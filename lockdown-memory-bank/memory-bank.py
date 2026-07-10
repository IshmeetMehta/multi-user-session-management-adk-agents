import os
import sys
import vertexai

# 1. Initialize environment variables 
PROJECT_ID = os.environ.get("GCP_PROJECT", "GCP_PROJECT_ID")
LOCATION = os.environ.get("GCP_REGION", "us-central1")

print(f"Connecting to Gemini Enterprise Agent Platform client in {LOCATION}...")
# Connect using the standardized enterprise platform initialization footprint
client = vertexai.Client(project=PROJECT_ID, location=LOCATION)

# ==========================================
# 2. PROVISION MEMORY BANK FOR AGENT A
# ==========================================
print("\n[Platform Engine] Provisioning Standalone Memory Bank for Agent A...")

try:
    bank_a = client.agent_engines.create(
        config={
            "display_name": "agent-a-memory-bank",
            "context_spec": {
                "memory_bank_config": {
                    # Explicitly leveraging natural language memory configurations out-of-the-box
                    "customization_configs": [
                        {"disable_natural_language_memories": False}
                    ]
                }
            }
        }
    )
    print("✅ Memory Bank A created successfully!")
    print(f"👉 RESOURCE_PATH_A: {bank_a.api_resource.name}")
except Exception as e:
    print(f"❌ Failed to provision Memory Bank A: {str(e)}")
    sys.exit(1)

# ==========================================
# 3. PROVISION MEMORY BANK FOR AGENT B
# ==========================================
print("\n[Platform Engine] Provisioning Standalone Memory Bank for Agent B...")

try:
    bank_b = client.agent_engines.create(
        config={
            "display_name": "agent-b-memory-bank",
            "context_spec": {
                "memory_bank_config": {
                    "customization_configs": [
                        {"disable_natural_language_memories": False}
                    ]
                }
            }
        }
    )
    print("✅ Memory Bank B created successfully!")
    print(f"👉 RESOURCE_PATH_B: {bank_b.api_resource.name}")
except Exception as e:
    print(f"❌ Failed to provision Memory Bank B: {str(e)}")
    sys.exit(1)

print("\n====================================================================")
print("COMPLETED: Both isolated backend engine paths are ready for GKE injection.")
print("====================================================================")