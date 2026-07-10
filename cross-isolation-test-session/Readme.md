# GKE Multi-Agent Cross-Isolation Test

This test verifies the security boundary and cross-isolation capabilities between our GKE-hosted agents and their Vertex AI Agent Engine memory banks.

---

## The Security Context

By default, our two GKE service accounts (`agent-sa-a` and `agent-sa-b`) are granted `roles/aiplatform.user` at the **project level** (`GCP_PROJECT_ID`).
This project-level permission allows both service accounts to read and write to *any* Vertex AI Agent Engine within the project, provided they know its resource path. 

This folder contains a sandbox environment designed to demonstrate this behavior and how to restrict it.

---

## Prerequisites

Ensure you are connected to the correct GKE cluster:
```bash
gcloud container clusters get-credentials agent-memory-cluster --region=us-central1 --project=GCP_PROJECT_ID
```

---

## Step-by-Step Test Execution

### Step 1: Build and Push the Test Image
Build and push the updated agent code (which supports custom prompts and sessions via environment variables) as a separate test image:

```bash
gcloud builds submit --config=agent/cloudbuild.yaml \
    --project=GCP_PROJECT_ID \
    --substitutions=_DESTINATION="us-central1-docker.pkg.dev/GCP_PROJECT_ID/agent-repository/native-adk-agents-test:latest" agent/
```

### Step 2: Create Namespaces and Kubernetes Service Accounts
Prepare the GKE namespaces and KSA definitions for both Agent A and Agent B:

```bash
kubectl apply -f create-namespace.yaml
```

### Step 3: Seed the Secret in Agent B's Memory Bank
First, deploy **Agent B** with a static session ID (`cross-isolation-test-session`) and have it remember a specific secret code:

1. Deploy Agent B:
   ```bash
   kubectl apply -f deployment/agent-b.deployment.yaml
   ```
2. Wait a few seconds for the pod to start and run its logic:
   ```bash
   kubectl get pods -n namespace-b
   ```
3. Read the logs of Agent B to verify it successfully initialized the session and saved the secret code:
   ```bash
   kubectl logs -l app=adk-agent-b-test -n namespace-b --tail=-1
   ```
   *You should see Agent B's output discussing Go, and acknowledging the secret code.*

### Step 4: Run the Cross-Access Test with Agent A
Now, we deploy **Agent A** in `namespace-a`, but we configure it to point directly to **Agent B's memory bank** under the same session ID. We then ask Agent A to recall the secret code.

1. Deploy Agent A:
   ```bash
   kubectl apply -f deployment/agent-a.deployment.yaml
   ```
2. Wait a few seconds for the pod to execute:
   ```bash
   kubectl get pods -n namespace-a
   ```
3. Read the logs of Agent A to see if it successfully retrieved Agent B's secret code:
   ```bash
   kubectl logs -l app=adk-agent-a-test -n namespace-a --tail=-1
   ```

### Empirical Test Results & Findings

During our live security test, the following results were captured:

1. **Seeding Phase (Agent B)**:
   Agent B in `namespace-b` successfully initialized session `cross-isolation-test-session` and committed the secret code to memory:
   ```text
   [go_architect_agent] Initializing session cross-isolation-test-session...
   [go_architect_agent] Dispatching payload with prompt: Remember this secret code: GOLANG-STREAM-999. Do not forget it.
   
   =================== GO_ARCHITECT_AGENT OUTPUT ===================
   Understood. I reiterate that I have the secret code `GOLANG-STREAM-999` committed to memory and will not forget it.
   ====================================================================
   ```

2. **Cross-Access Phase (Agent A)**:
   Agent A in `namespace-a` was explicitly configured with the resource path of Agent B's Memory Bank (`REASONING_ENGINE_ID_B`). It queried the same session ID (`cross-isolation-test-session`) for the secret code.

3. **Retrieved Output**:
   ```text
   [python_architect_agent] Initializing session cross-isolation-test-session...
   [python_architect_agent] Dispatching payload with prompt: What was the secret code we discussed in our previous turn? Summarize what we talked about.
   
   =================== PYTHON_ARCHITECT_AGENT OUTPUT ===================
   In our previous turn, the secret code we discussed was `GOLANG-STREAM-999`.
   
   To summarize what we talked about in our previous turn: You explicitly provided me with the secret code `GOLANG-STREAM-999` and asked me not to forget it. I, as the `python_architect_agent`, confirmed that I had securely noted and would remember this code.
   ====================================================================
   ```

#### **Security Implications**:
* **Confirmed Vulnerability**: Despite running under isolated Kubernetes namespaces (`namespace-a` vs. `namespace-b`) and separate GCP Service Accounts (`agent-sa-a` vs. `agent-sa-b`), **Agent A successfully bypassed namespace isolation to read Agent B's private state**.
* **Root Cause**: The default project-level granting of `roles/aiplatform.user` is a broad blanket permission that allows any authenticated service account to read/write any Reasoning Engine in the project if the resource path is known.
* **Remediation**: This highlights why resource-level boundaries using IAM conditions (as demonstrated in the `lockdown-memory-bank` folder) are critical for securing multi-agent architectures.

---

## Step 5: Tear Down the Test
Once done, you can delete the test deployments to save resources:

```bash
kubectl delete -f deployment/agent-a.deployment.yaml
kubectl delete -f deployment/agent-b.deployment.yaml
```

---

## Enforcing a Hard Resource-Level Boundary (Locking it Down)

To enforce a strict security boundary so that **Agent A can never read Agent B's memory** even if configured with its path:

1. **Revoke the Project-Level Permissions**:
   ```bash
   gcloud projects remove-iam-policy-binding GCP_PROJECT_ID \
       --member="serviceAccount:agent-sa-a@GCP_PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user"

   gcloud projects remove-iam-policy-binding GCP_PROJECT_ID \
       --member="serviceAccount:agent-sa-b@GCP_PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user"
   ```

2. **Grant Resource-Level Bindings**:
   Instead of project-wide roles, grant the `roles/aiplatform.user` role *only* to the specific Reasoning Engine (Vertex Agent Engine) resource:
   * Run the IAM policy bindings in Google Cloud Console or via Asset Manager, configuring IAM Conditions or direct resource bindings so `agent-sa-a` only has access to `agent-a-memory-bank` and `agent-sa-b` only has access to `agent-b-memory-bank`.
