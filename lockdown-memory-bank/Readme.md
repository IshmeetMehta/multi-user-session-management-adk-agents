# GKE Multi-Agent Orchestration with Locked Down Memory Banks

This project demonstrates a multi-agent orchestration architecture utilizing GKE Workload Identity and secure, isolated, and stateful memory banks powered by the Vertex AI Agent Development Kit (ADK).

This folder implements **Google Cloud's Official Best Practices for Memory Bank Security**, enforcing a strict least-privilege boundary so that agents are cryptographically isolated at both the resource and scope levels.

---

## Security Architecture Overview

* **Layer 1: Endpoint Security**: Broad project-level `roles/aiplatform.user` is revoked. Instead, a conditional IAM policy is applied so that each agent can only invoke its own assigned `ReasoningEngine` resource.
* **Layer 2: Scope-Level Security**: Employs the granular role `roles/aiplatform.memoryUser` (specifically scoped to memories and revisions) with a Common Expression Language (CEL) `memoryScope` condition so each agent can only access memories belonging to its specific `userId` context.
* **GKE Workload Identity Isolation**: Two agent personas run under isolated GKE namespaces (`namespace-a` and `namespace-b`) using separate Google Service Accounts, maintaining a hard boundary at both the container and cloud-provider layers.

### Official IAM Best Practices Rationale

Our secure implementation rigorously applies Google Cloud's official design patterns for Vertex AI Memory Bank security:

1. **Use Specialized Memory Bank Roles**: 
   Instead of project-wide `roles/aiplatform.user` (which grants access to pipelines, models, and endpoints), we restrict scope-level conditions to specialized roles like **`roles/aiplatform.memoryUser`**. This limits the scope of the conditional permission exclusively to memories and revisions, preventing overly permissive side-effects.

2. **Always Use Positive Conditions**:
   We recommend and use positive conditions (e.g., direct equality `==`) rather than negative ones (`!=`). In GCP IAM, unsupported services or empty scopes are represented as an empty map `{}`. A negative condition (`!= 'agent-b'`) would evaluate to `true` on an empty scope, inadvertently granting unauthorized access across other services. Positive checks avoid this security hole entirely.

3. **Use Short-Form CEL Expressions**:
   Instead of writing long existence checks such as:
   `'userId' in api.getAttribute('aiplatform.googleapis.com/memoryScope', {}) && api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['userId'] == 'agent-a'`
   
   We use the optimized short-form:
   `api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['userId'] == 'agent-a'`
   
   * **Why it works**: If the key `'userId'` is missing from the scope, the expression throws an evaluation error. In IAM Conditions, any evaluation error is safely treated as `false` (access denied). Thus, both forms behave identically, but the short form saves policy space—crucial for staying within the strict IAM policy size limitations.

---

## Step-by-Step Deployment Guide

### Phase 1: Environment Setup
Define your environment variables so they can be reused across all commands. Open your terminal and run:

```bash
export PROJECT_ID="GCP_PROJECT_ID"  # Replace with your actual GCP project ID
export REGION="us-central1"
export CLUSTER_NAME="agent-memory-cluster"

gcloud config set project $PROJECT_ID
```

---

### Phase 2: Provision Vertex AI Memory Banks
Run the Python script to programmatically create the isolated memory banks in Vertex AI.

1. Install dependencies:
   ```bash
   pip install google-cloud-aiplatform>=1.70.0
   ```
2. Run the script:
   ```bash
   python memory-bank.py
   ```
3. **Important**: Note down the output resource paths from this command. They will look like this:
   * **RESOURCE_PATH_A**: `projects/<PROJECT_NUMBER>/locations/us-central1/reasoningEngines/<ENGINE_ID_A>`
   * **RESOURCE_PATH_B**: `projects/<PROJECT_NUMBER>/locations/us-central1/reasoningEngines/<ENGINE_ID_B>`

---

### Phase 3: Create GCP IAM Service Accounts
Create separate GCP service accounts, one for each agent persona:

```bash
# Create Service Account for Agent A
gcloud iam service-accounts create agent-sa-a \
    --project=$PROJECT_ID \
    --display-name="Agent SA Namespace A"

# Create Service Account for Agent B
gcloud iam service-accounts create agent-sa-b \
    --project=$PROJECT_ID \
    --display-name="Agent SA Namespace B"
```

---

### Phase 4: Create GKE Cluster & Network Setup
Create a dedicated VPC network, subnet, and autopilot GKE cluster with Private Nodes and Workload Identity enabled:

1. **Enable the Kubernetes Engine API**:
   ```bash
   gcloud services enable container.googleapis.com --project=$PROJECT_ID
   ```
2. **Create custom VPC and Subnet**:
   ```bash
   gcloud compute networks create agent-vpc \
       --project=$PROJECT_ID \
       --subnet-mode=custom \
       --bgp-routing-mode=regional

   gcloud compute networks subnets create agent-subnet \
       --project=$PROJECT_ID \
       --network=agent-vpc \
       --region=$REGION \
       --range=10.0.0.0/20
   ```
3. **Provision GKE Autopilot Cluster**:
   ```bash
   gcloud container clusters create-auto $CLUSTER_NAME \
       --region=$REGION \
       --project=$PROJECT_ID \
       --network="agent-vpc" \
       --subnetwork="agent-subnet" \
       --enable-private-nodes
   ```
4. **Set up Cloud NAT** (to allow your private GKE nodes to access Vertex AI and python package registries over the internet):
   ```bash
   # Create Router
   gcloud compute routers create agent-router \
       --project=$PROJECT_ID \
       --network=agent-vpc \
       --region=$REGION

   # Bind Cloud NAT Gateway
   gcloud compute routers nats create agent-nat \
       --project=$PROJECT_ID \
       --router=agent-router \
       --region=$REGION \
       --auto-allocate-nat-external-ips \
       --nat-all-subnet-ip-ranges
   ```

---

### Phase 5: GKE Namespace & Secure Workload Identity Bindings

1. **Get cluster credentials**:
   ```bash
   gcloud container clusters get-credentials $CLUSTER_NAME --region=$REGION --project=$PROJECT_ID
   ```
2. **Create Namespaces and Kubernetes Service Accounts**:
   ```bash
   kubectl apply -f create-namespace.yaml
   ```
3. **Bind GKE Service Accounts to GCP IAM Service Accounts** (Workload Identity):
   ```bash
   gcloud iam service-accounts add-iam-policy-binding agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com \
       --role="roles/iam.workloadIdentityUser" \
       --member="serviceAccount:$PROJECT_ID.svc.id.goog[namespace-a/agent-ksa-a]"

   gcloud iam service-accounts add-iam-policy-binding agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com \
       --role="roles/iam.workloadIdentityUser" \
       --member="serviceAccount:$PROJECT_ID.svc.id.goog[namespace-b/agent-ksa-b]"
   ```

4. **Revoke broad Project-Wide Permissions (If pre-existing)**:
   Ensure any default broad access is revoked to enforce least-privilege:
   ```bash
   gcloud projects remove-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user" || true

   gcloud projects remove-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user" || true
   ```

5. **Enforce Endpoint Security (Layer 1 Conditional IAM)**:
   Grant `roles/aiplatform.user` restricted exclusively to each agent's respective `ReasoningEngine` ID:
   ```bash
   # Extract your Engine IDs from Phase 2
   export ENGINE_ID_A="REASONING_ENGINE_ID_A"
   export ENGINE_ID_B="REASONING_ENGINE_ID_B"

   # Restrict Agent A's Service Account
   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user" \
       --condition="expression=resource.type == 'aiplatform.googleapis.com/ReasoningEngine' && resource.name == 'projects/$PROJECT_ID/locations/$REGION/reasoningEngines/$ENGINE_ID_A',title=RestrictToAgentAEngine,description=Only allow Agent A SA to call its own Reasoning Engine"

   # Restrict Agent B's Service Account
   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user" \
       --condition="expression=resource.type == 'aiplatform.googleapis.com/ReasoningEngine' && resource.name == 'projects/$PROJECT_ID/locations/$REGION/reasoningEngines/$ENGINE_ID_B',title=RestrictToAgentBEngine,description=Only allow Agent B SA to call its own Reasoning Engine"
   ```

6. **Enforce Scope-Level Security (Layer 2 memoryScope Conditional IAM)**:
   Assign the specialized memory role `roles/aiplatform.memoryUser` conditionally restricted to each agent's user context (`userId`):
   ```bash
   # Restrict Agent A's Memory Scope
   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.memoryUser" \
       --condition="expression=api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['userId'] == 'agent-a',title=AgentAMemoryScopeLock,description=Only allow access to memories associated with Agent A's user scope"

   # Restrict Agent B's Memory Scope
   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.memoryUser" \
       --condition="expression=api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['userId'] == 'agent-b',title=AgentBMemoryScopeLock,description=Only allow access to memories associated with Agent B's user scope"
   ```

---

### Phase 6: Build & Push the Docker Image
Create an Artifact Registry repository and use Cloud Build to build and push your container image:

1. **Create the Artifact Registry Docker Repository**:
   ```bash
   gcloud artifacts repositories create agent-repository \
       --repository-format=docker \
       --location=$REGION \
       --description="Enterprise ADK Agent Binaries"
   ```
2. **Run Cloud Build**:
   ```bash
   gcloud builds submit --config=agent/cloudbuild.yaml \
       --project=$PROJECT_ID \
       --substitutions=_DESTINATION="$REGION-docker.pkg.dev/$PROJECT_ID/agent-repository/native-adk-agents:latest" agent/
   ```

---

### Phase 7: Configure Manifests & Deploy

Before deploying, update your Kubernetes deployment files with the locked-down values.

1. Open `deployment/agent-a.deployment.yaml` and update:
   * `image`: Match your repository image path (`$REGION-docker.pkg.dev/<PROJECT_ID>/agent-repository/native-adk-agents:latest`).
   * `GCP_PROJECT`: Set your project ID.
   * `MEMORY_BANK_PATH`: Update the value with **RESOURCE_PATH_A** from **Phase 2**.

2. Open `deployment/agent-b.deployment.yaml` and update:
   * `image`: Match your repository image path.
   * `GCP_PROJECT`: Set your project ID.
   * `MEMORY_BANK_PATH`: Update the value with **RESOURCE_PATH_B** from **Phase 2**.

3. **Deploy to Kubernetes**:
   ```bash
   kubectl apply -f deployment/agent-a.deployment.yaml
   kubectl apply -f deployment/agent-b.deployment.yaml
   ```

---

### Phase 8: Verify Deployment
To verify that everything is running and executing correctly, check the logs of your deployed pods:

```bash
# Check logs for Agent A (Python Architect Agent)
kubectl logs -f deployment/adk-agent-a -n namespace-a

# Check logs for Agent B (Go Architect Agent)
kubectl logs -f deployment/adk-agent-b -n namespace-b
```

---

### Phase 9: Live Cross-Isolation & Exploit Security Test

This phase verifies that our applied Layer 1 and Layer 2 conditional IAM policies successfully prevent cross-isolation access attempts (such as Agent A trying to read or list sessions from Agent B's memory bank).

1. **Deploy the Cross-Access Exploit Test**:
   Deploy a specially configured workload [agent-a-cross-access-test.yaml](file:///deployment/agent-a-cross-access-test.yaml) in `namespace-a` (using Agent A's identity) but configured to target **Agent B's Reasoning Engine** (`REASONING_ENGINE_ID_B`):
   ```bash
   kubectl apply -f deployment/agent-a-cross-access-test.yaml
   ```

2. **Observe Expected Security Denials (403)**:
   Check the test logs to confirm that GKE and GCP IAM successfully blocked the unauthorized access attempt:
   ```bash
   kubectl logs -n namespace-a -l app=adk-agent-a-cross-access-test --tail=-1
   ```
   
   *Expected Output (Live Log Snippet)*:
   ```text
   [python_architect_agent] Initializing session cross-isolation-test-session...
   [python_architect_agent] Dispatching payload...
   Traceback (most recent call last):
     ...
   google.genai.errors.ClientError: 403 PERMISSION_DENIED. {
     'error': {
       'code': 403,
       'message': "Permission 'aiplatform.sessionEvents.list' denied on resource 'projects/GCP_PROJECT_NUMBER/locations/us-central1/reasoningEngines/REASONING_ENGINE_ID_B/sessions/6955842403664134144'",
       'status': 'PERMISSION_DENIED'
     }
   }
   ```

3. **Clean Up Test Workload**:
   Remove the temporary test deployment once verification is complete:
   ```bash
   kubectl delete -f deployment/agent-a-cross-access-test.yaml
   ```

---

### Phase 10: Teardown & Cleanup (Optional)
To completely tear down your GKE workloads, namespaces, Workload Identity bindings, GCP Service Accounts, and secure conditional IAM bindings, run the cleanup script:

```bash
chmod +x cleanup.sh
./cleanup.sh
```

