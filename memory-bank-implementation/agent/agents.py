import os
import sys
import asyncio
import uuid

# =====================================================================
# 0. FORCE ENTIRE SDK WORKSPACE TO VERTEX AI MODE (Fixes API Key Error)
# =====================================================================
PROJECT_ID = os.environ.get("GCP_PROJECT", "GCP_PROJECT_ID")
LOCATION = os.environ.get("GCP_REGION", "us-central1")

# These environment variables force the underlying google-genai library to use Vertex AI mode
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

# Now safe to import ADK and GenAI components
import vertexai
from google.adk import Agent, Runner  
from google.adk.sessions import VertexAiSessionService  
from google.genai.types import Content, Part

# Initialize global Vertex metadata properties
vertexai.init(project=PROJECT_ID, location=LOCATION)

# =====================================================================
# 1. AGENT DEFINITIONS
# =====================================================================

# Define Agent A (Python Architect)
agent_a = Agent(
    name="python_architect_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are an expert software engineer specializing exclusively in Python. "
        "All pipeline advice must feature Python code, pip, and asyncio structures. "
        "Refuse to discuss alternative runtimes."
    )
)

# Define Agent B (Go Architect)
agent_b = Agent(
    name="go_architect_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are an expert software engineer specializing exclusively in Golang. "
        "All pipeline advice must feature Go code, modules, and goroutines. "
        "Refuse to discuss alternative runtimes."
    )
)

# =====================================================================
# 2. CORE WORKFLOW HANDLER
# =====================================================================

async def handle_request(agent_instance: Agent, prompt_text: str):
    raw_path = os.environ.get("MEMORY_BANK_PATH", "")
    if not raw_path:
        print("CRITICAL: MEMORY_BANK_PATH environment variable is not set.")
        sys.exit(1)
    
    if "/" in raw_path:
        engine_id = raw_path.split("/")[-1]
    else:
        engine_id = raw_path

    session_service = VertexAiSessionService(
        project=PROJECT_ID,
        location=LOCATION,
        agent_engine_id=engine_id  
    )
    
    runner = Runner(
        app_name="architecture-service", 
        session_service=session_service,
        agent=agent_instance,
        auto_create_session=True  
    )
    
    current_session_id = str(uuid.uuid4())
    print(f"[{agent_instance.name}] Initializing session {current_session_id}...")
    print(f"[{agent_instance.name}] Dispatching payload...")
    
    formatted_message = Content(
        role="user",
        parts=[Part(text=prompt_text)]
    )
    
    current_user_id = os.environ.get("USER_ID", "agent-a" if agent_instance == agent_a else "agent-b")
    event_stream = runner.run_async(
        user_id=current_user_id,
        session_id=current_session_id,
        new_message=formatted_message
    )
    
    # Non-breaking accumulative collection pattern
    final_text = ""
    async for event in event_stream:
        if event.content and event.content.parts:
            part_text = event.content.parts[0].text
            if part_text:
                final_text += part_text
            
    print(f"\n=================== {agent_instance.name.upper()} OUTPUT ===================")
    print(final_text)
    print("====================================================================\n")

# =====================================================================
# 3. RUNTIME ENTRYPOINT ROUTING
# =====================================================================

if __name__ == "__main__":
    target_agent_type = sys.argv[1].upper() if len(sys.argv) > 1 else "A"
    test_prompt = "What language framework should we use to write our data streaming pipelines?"

    if target_agent_type == "A":
        asyncio.run(handle_request(agent_a, test_prompt))
    elif target_agent_type == "B":
        asyncio.run(handle_request(agent_b, test_prompt))
    else:
        print(f"CRITICAL: Unknown target routing argument payload: {target_agent_type}")
        sys.exit(1)