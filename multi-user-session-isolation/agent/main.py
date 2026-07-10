import os
import logging
from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, auth
import httpx
from google.oauth2 import credentials as google_creds
from google.adk import Agent, Runner
from google.adk.models import Gemini
from google.adk.sessions import VertexAiSessionService
from google.genai.types import Content, Part
import vertexai

# 1. Initialize Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("multi-user-agent")

# 2. Initialize Firebase Admin SDK
try:
    firebase_admin.initialize_app()
    logger.info("✅ Firebase Admin SDK initialized successfully!")
except Exception as e:
    logger.warning(f"⚠️ Firebase default initialization failed, using local fallback setup: {e}")
    try:
        firebase_admin.initialize_app(credentials.Certificate({
            "type": "service_account",
            "project_id": os.environ.get("GCP_PROJECT", "GCP_PROJECT_ID"),
        }))
        logger.info("✅ Fallback Firebase Admin initialized.")
    except Exception as ex:
        logger.error(f"❌ Failed to initialize Firebase Admin SDK: {ex}")

# 3. Initialize FastAPI App
app = FastAPI(
    title="Multi-User Session-Isolated Agent Backend",
    description="FastAPI service enforcing secure end-to-end multi-tenant session isolation with Vertex AI.",
    version="1.0.0"
)

# Enable CORS for local and production frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ID = os.environ.get("GCP_PROJECT", "GCP_PROJECT_ID")
LOCATION = os.environ.get("GCP_REGION", "us-central1")

# Force Vertex AI mode on google-genai
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

vertexai.init(project=PROJECT_ID, location=LOCATION)

# Custom Session Service using Delegated Credentials
class DelegatedVertexAiSessionService(VertexAiSessionService):
    def __init__(self, *args, credentials=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._credentials = credentials

    def _get_api_client(self):
        import vertexai
        return vertexai.Client(
            project=self._project,
            location=self._location,
            credentials=self._credentials,
            http_options=self._api_client_http_options_override(),
        ).aio

# Custom Gemini Model using Delegated Credentials
class DelegatedGemini(Gemini):
    def __init__(self, *args, credentials=None, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "_credentials", credentials)

    @property
    def api_client(self):
        from google.genai import Client as GenAiClient
        return GenAiClient(
            project=PROJECT_ID,
            location=LOCATION,
            credentials=self._credentials
        )

# 4. Dependency: Authenticate with Google OAuth Access Token and retrieve user email
async def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Must be 'Bearer <Google_Access_Token>'."
        )
    
    token = authorization.split("Bearer ")[1]
    
    # 🚨 Verification Plan (Solution A): Exchange Bearer token with Google Token Info Endpoint
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": token}
            )
            if response.status_code != 200:
                logger.error(f"Google tokeninfo verification failed: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired Google OAuth Access Token."
                )
            
            token_info = response.json()
            email = token_info.get("email")
            if not email:
                logger.error(f"Google tokeninfo response missing email: {token_info}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google OAuth Access Token is missing the email scope."
                )
            return email
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication Failed: {str(e)}"
        )

async def get_user_credentials(authorization: str = Header(None)) -> google_creds.Credentials:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header."
        )
    token = authorization.split("Bearer ")[1]
    return google_creds.Credentials(token)

# 5. Pydantic Request Models
class ChatRequest(BaseModel):
    session_key: str
    prompt: str

# 6. API Route: Chat with Session Isolation
@app.post("/api/chat")
async def chat_endpoint(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    user_creds: google_creds.Credentials = Depends(get_user_credentials)
):
    # ─── THE SECURE SESSION BOUNDARY (With Regex Sanitization for @ and .) ───
    import re
    sanitized_user = re.sub(r'[^A-Za-z0-9-]', '-', user_id).lower()
    sanitized_key = re.sub(r'[^A-Za-z0-9-]', '-', request.session_key).lower()
    secured_session_id = f"user-{sanitized_user}-session-{sanitized_key}"
    logger.info(f"Received chat request from user [{user_id}] for session key [{request.session_key}] -> Mapped to: {secured_session_id}")
    
    # Target Memory Bank (Reasoning Engine) from Environment
    engine_id = os.environ.get("MEMORY_BANK_PATH")
    if not engine_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: MEMORY_BANK_PATH is not configured."
        )
    
    if "/" in engine_id:
        engine_id = engine_id.split("/")[-1]

    try:
        # Initialize the session service with delegated end-user credentials
        session_service = DelegatedVertexAiSessionService(
            project=PROJECT_ID,
            location=LOCATION,
            agent_engine_id=engine_id,
            credentials=user_creds
        )
        
        # Initialize model with delegated credentials to pass IAM memoryScope checks
        model = DelegatedGemini(
            model="gemini-2.5-flash",
            credentials=user_creds
        )
        
        # Initialize Agent
        agent = Agent(
            name="multi_user_agent",
            model=model,
            instruction="You are a helpful and stateful corporate assistant. Always keep track of user context."
        )
        
        # Initialize Runner
        runner = Runner(
            app_name="multi-user-session-isolated-agent",
            session_service=session_service,
            agent=agent,
            auto_create_session=True
        )
        
        formatted_message = Content(
            role="user",
            parts=[Part(text=request.prompt)]
        )
        
        # Enforce memoryScope via user_id matching OIDC email
        event_stream = runner.run_async(
            user_id=user_id,
            session_id=secured_session_id,
            new_message=formatted_message
        )
        
        final_text = ""
        async for event in event_stream:
            if event.content and event.content.parts:
                part_text = event.content.parts[0].text
                if part_text:
                    final_text += part_text
                    
        return {
            "status": "success",
            "session_id": secured_session_id,
            "response": final_text
        }
        
    except Exception as e:
        logger.error(f"Error executing agent session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent Execution Failure: {str(e)}"
        )

# 7. Health Check
@app.get("/health")
def health():
    return {"status": "healthy"}
