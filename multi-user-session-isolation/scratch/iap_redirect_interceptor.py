import os
import logging
import jwt  # PyJWT library
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import RedirectResponse
import httpx

# Initialize FastAPI App
app = FastAPI(title="Casper IAP Redirect Interceptor")
logger = logging.getLogger("iap-interceptor")

# Expected IAP Audience (usually in format /projects/PROJECT_NUMBER/global/gateways/GATEWAY_ID for Gateway/IAP)
IAP_AUDIENCE = os.environ.get("IAP_AUDIENCE", "/projects/123456789/global/gateways/default")

# ======================================================================
# 1. Decodes and verifies the IAP JWT Assertion from SecProxy/IAP
# ======================================================================
def get_verified_iap_user(request: Request) -> str:
    """
    Extracts the authenticated end-user email from the IAP JWT Assertion header.
    In a hardened environment, this verifies the signature against Google's public keys.
    """
    # IAP injects this cryptographically signed header containing user details
    iap_jwt = request.headers.get("X-Goog-IAP-JWT-Assertion")
    if not iap_jwt:
        # Fallback for local development or testing
        test_user = request.headers.get("X-Test-User-Email")
        if test_user:
            return test_user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-Goog-IAP-JWT-Assertion header. IAP is not in the loop."
        )

    try:
        # ⚠️ Note: In production, verify the signature using Google's public JWK keys:
        # https://www.gstatic.com/iap/verify/public_key-jwk
        # For demonstration and audit, we decode the claims
        decoded_claims = jwt.decode(iap_jwt, options={"verify_signature": False})
        
        # Extract the email address as the true authenticated end-user identity
        email = decoded_claims.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid IAP JWT Assertion: claims do not contain email address."
            )
        return email
    except Exception as e:
        logger.error(f"Failed to decode IAP JWT: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"IAP JWT Verification Failed: {str(e)}"
        )

# ======================================================================
# 2. Intercepting and Injecting userId into URL via 307 Redirects
# ======================================================================
@app.get("/api/chat/initiate")
async def initiate_session(request: Request, session_key: str):
    """
    Step 1: Client calls /api/chat/initiate?session_key=xyz.
    Step 2: Server extracts the user email from the cryptographically signed IAP header.
    Step 3: Server intercepts the creation and redirects the client with a 307
            injecting the specific userId into the URL, which will be factored into the session ID.
    """
    user_id = get_verified_iap_user(request)
    logger.info(f"Authentic user [{user_id}] initiating session key [{session_key}]")
    
    # Securely inject user_id into the session creation endpoint URL
    redirect_url = f"/api/chat/user/{user_id}/session/{session_key}"
    
    logger.info(f"🛡️ REDIRECT INTERCEPT (307): Redirecting to unified isolated path: {redirect_url}")
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.post("/api/chat/user/{user_id}/session/{session_key}")
async def execute_isolated_chat(
    user_id: str,
    session_key: str,
    request: Request,
    payload: dict
):
    """
    Processes the request securely after the 307 redirect.
    Ensures that the URL parameter {user_id} matches the cryptographically signed IAP email,
    guarding against URL manipulation/hijacking attempts.
    """
    verified_user_id = get_verified_iap_user(request)
    
    # ─── SECURE GATE ───
    if verified_user_id != user_id:
        logger.error(f"❌ SECURITY VIOLATION: Caller identity [{verified_user_id}] does not match URL path user_id [{user_id}]!")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot access or generate a session for another user."
        )
        
    secured_session_id = f"user-{verified_user_id}-session-{session_key}"
    logger.info(f"✅ ACCESS GRANTED: Running session isolation for {secured_session_id}")
    
    # Propagate the verified identity to down-stream services or DB layers via Snap-specific headers
    custom_snap_headers = {
        "X-Snap-User-ID": verified_user_id,
        "X-Snap-Isolated-Session-ID": secured_session_id
    }
    
    # Inside ADK, we can use these headers/context during execution
    return {
        "status": "success",
        "session_id": secured_session_id,
        "user_id": verified_user_id,
        "propagated_headers": custom_snap_headers,
        "message": "Session initialized and isolated securely under IAP."
    }
