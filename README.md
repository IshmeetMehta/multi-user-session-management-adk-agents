# Vertex AI Multi-Agent Session Management & Memory Isolation (ADK)

This repository contains a comprehensive suite of implementations, manifests, and test harnesses demonstrating how to orchestrate stateful AI agents with complete multi-tenant, multi-user session and memory isolation. Built using the **Vertex AI Agent Development Kit (ADK)** and stateful **Memory Banks**, this architecture combines App-Layer validation with Cloud-Layer IAM boundaries to construct a robust, production-ready defense-in-depth framework.

---

## 🗺️ Project Directory Roadmap

The repository is structured into isolated modules, each demonstrating key security configurations, implementations, and testing patterns:

```
├── .gitignore                                # Excludes virtual environments and local cache artifacts
├── Diagram.md                                # Architectural session-isolation dataflow diagram (Base64)
├── iam-policy.yaml                           # Consolidated project-level GCP IAM service account policy bindings
├── alice-engine-cond.yaml                    # IAM CEL conditions restricting Alice to her dedicated Reasoning Engine
├── bob-engine-cond.yaml                      # IAM CEL conditions restricting Bob to his dedicated Reasoning Engine
├── alice-memory-cond.yaml                    # IAM CEL conditions restricting Alice's memory scope access
├── bob-memory-cond.yaml                      # IAM CEL conditions restricting Bob's memory scope access
│
├── memory-bank-implementation/               # Core stateful memory bank module implementation
│   ├── agent/                                # Main python script, Dockerfile, and package requirements
│   ├── deployment/                           # GKE Deployment manifests for agent instances
│   └── Readme.md                             # Initialization and deployment guide for memory bank
│
├── lockdown-memory-bank/                     # IAM-restricted memory bank deployment pattern
│   ├── agent/                                # Stateful Agent ADK definition and tools
│   ├── deployment/                           # Secure GKE Deployment configurations and cross-access test Pods
│   └── Readme.md                             # Step-by-step instructions for enforcing policy lockdowns
│
├── cross-isolation-test-session/             # Basic multi-agent runtime isolation check
│   ├── agent/                                # Agent ADK configuration and Docker container
│   ├── deployment/                           # GKE deployment manifests for Agent A and Agent B
│   └── Readme.md                             # Setup guide and instructions
│
└── multi-user-session-isolation/             # End-to-End Multi-Tenant Full-Stack Web Application
    ├── agent/                                # Secure FastAPI python backend using Firebase JWT validation
    ├── frontend/                             # Premium glassmorphic web UI with Firebase Auth Google Sign-In
    ├── deployment/                           # GKE deployment, services, and exploit verification pods
    ├── test_isolation_exploit.py             # Active python simulation auditing and verifying isolation boundaries
    ├── production_readiness.md               # Enterprise compliance, quotas, and production rollout checklist
    └── Readme.md                             # Detailed setup, build, and deployment walkthrough
```

---

## 🛡️ Security Scenarios & Matrix

The architecture defines four primary deployment scenarios matching different corporate isolation, security, and cost profiles:

| Scenario | Use Case | Reasoning Engine Isolation | Memory Scope Isolation | Required Roles | CEL Condition Needed? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Scenario A** | Administrators, developers, or global non-isolated pipelines | **Shared / Unrestricted** | **Shared / Unrestricted** | `roles/aiplatform.user` | **No** (Unconditional) |
| **Scenario B** | Basic backend services that only perform predictions / LLM generation | **None** (No engine used) | **None** (No memory used) | `roles/aiplatform.endpoints.predictUser` | **No** (Unconditional) |
| **Scenario C** | Full-isolation tenants (e.g., highly sensitive separate client pods) | **Dedicated** (Per-agent resource) | **Dedicated** (Isolated logical scope) | `roles/aiplatform.user`<br>`roles/aiplatform.memoryUser` | **Yes** (Resource + Scope Lock) |
| **Scenario D** | Cost-optimized multi-tenant pods (e.g., separate users sharing one agent framework) | **Shared** (Same physical runtime engine) | **Dedicated** (Isolated logical scope) | `roles/aiplatform.user`<br>`roles/aiplatform.memoryUser` | **Yes** (Shared Engine + Scope Lock) |

For a deep dive into each scenario's IAM properties, refer to the [Scenario IAM Architecture Guide](file:///usr/local/google/home/ishmeetm/multi-user-session-management-adk-agents/security_scenarios.md).

---

## 🔒 Defense-in-Depth Strategy

To enforce absolute session isolation, the architecture relies on a strict two-layer boundary model:

```mermaid
graph TD
    subgraph Layer 1: Application-Level Defense (Web Frontend & FastAPI)
        User[End User (Google OIDC)] -->|1. Sign In & Prompt| Front["Web Frontend (Firebase Auth)"]
        Front -->|2. Send JWT ID Token + Friendly Key| API["FastAPI Backend (GKE)"]
        API -->|3. Decode & Verify JWT Local Signature| Auth{"Valid Token?"}
        Auth -->|No| Reject["403 Unauthorized"]
        Auth -->|Yes: Extract User ID| Prefix["4. Format Session ID: user-EMAIL-session-KEY"]
    end

    subgraph Layer 2: Cloud-Level Defense (GCP IAM CEL Gate)
        Prefix -->|5. Connect via Delegated Credentials| Vertex["Vertex AI (Reasoning Engine / Memory Bank)"]
        Vertex -->|6. Intercept Session Call| IAM{"GCP IAM CEL Policy Engine"}
        IAM -->|Match user ID in memoryScope?| Write["Allow Memory Write & Persistent Chat Turn"]
        IAM -->|Mismatch / Compromised Backend| Block["Deny Access (403 Permission Denied)"]
    end
    
    style User fill:#ea4335,stroke:#333,stroke-width:2px,color:#fff
    style Reject fill:#ff9900,stroke:#333,stroke-width:2px,color:#fff
    style Block fill:#ea4335,stroke:#333,stroke-width:2px,color:#fff
    style Write fill:#34a853,stroke:#333,stroke-width:2px,color:#fff
```

### 1. Application-Layer Validation (The Shield)
*   **Firebase Authentication (JWT)**: Users authenticate on the glassmorphic frontend using Google Sign-In. The resulting cryptographically signed JWT token is securely verified in the backend via `firebase-admin`.
*   **Secure Session ID Formatting**: Users cannot specify raw session names. FastAPI intercepts the verified identifier (e.g., `alice@yourdomain.com`) and prefixes the target session ID programmatically:
    ```
    user-alice@yourdomain.com-session-my-friendly-key
    ```
    This completely redirects malicious actors attempting session hijacking to their own separate database namespaces.

### 2. Cloud-Layer IAM Constraints (The Absolute Safety Net)
Even if an attacker gains full control of your backend pod runtime, they cannot query another user's session from the stateful Memory Bank. We leverage GCP IAM with **Common Expression Language (CEL)** to bind the session client down to its designated resource and memory scope:

*   **Dedicated Reasoning Engine Access (Layer 1 Lock):**
    ```yaml
    expression: >
      !has(resource.name) || (has(resource.name) && (
        resource.name.startsWith('projects/GCP_PROJECT_ID/locations/us-central1/reasoningEngines/REASONING_ENGINE_ID_A') ||
        resource.name.startsWith('projects/GCP_PROJECT_ID/locations/us-central1/publishers/')
      ))
    ```
*   **Dedicated Memory Scope Access (Layer 2 Lock):**
    ```yaml
    expression: >
      api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['userId'] == 'agent-a'
    ```

---

## 🚀 Deployment & Build Commands

### Backend Container Build
Deploy your container images to **Artifact Registry** using Google Cloud Build:
```bash
gcloud builds submit multi-user-session-isolation/agent/ \
    --config=multi-user-session-isolation/agent/cloudbuild.yaml \
    --substitutions=_DESTINATION="us-central1-docker.pkg.dev/GCP_PROJECT_ID/agent-repository/multi-user-isolated-agent:latest"
```

### Exposing GKE Workloads
Apply the Kubernetes manifests to route ingress and connect pods through GKE Workload Identity:
```bash
kubectl apply -f multi-user-session-isolation/deployment/multi-user-agent.yaml
```

---

## 🧪 Verification & Exploit Testing

To verify the strength of the isolation boundaries, the project includes an active **Exploit Auditing Script** (`test_isolation_exploit.py`) that programmatically simulates:
1.  **App-Layer Key Hijacking**: Simulates a client requesting cross-user sessions through FastAPI.
2.  **Direct Database Bypass**: Simulates a compromised container bypassing application checks entirely, connecting directly to Vertex AI, and trying to pull another user's logical session ID using unauthorized OIDC context credentials.

### Run the Exploit Test Locally:
Make sure your environment is configured for GCP:
```bash
# Setup your environment variables
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/sa-key.json"
export GCP_PROJECT="GCP_PROJECT_ID"
export GCP_REGION="us-central1"

# Run the python validation suite
python3 multi-user-session-isolation/test_isolation_exploit.py
```

> [!NOTE]
> The test verifies that any unauthorized cross-tenant read/write immediately results in an expected `403 Permission Denied` block by the GCP IAM Policy engine, confirming mathematical security isolation.
