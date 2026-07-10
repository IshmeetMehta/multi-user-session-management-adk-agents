# GKE Multi-Agent Orchestration with Vertex AI Memory Banks

This project demonstrates a multi-agent orchestration architecture utilizing GKE Workload Identity and isolated, stateful memory banks powered by the Vertex AI Agent Development Kit (ADK).

---

## Architecture Overview

* **Isolated Memory Banks**: Dedicated long-term natural language memory banks are provisioned programmatically in Vertex AI under region `us-central1`.
* **GKE Workload Identity Isolation**: Two agent personas run under isolated Kubernetes namespaces (`namespace-a` and `namespace-b`). Each namespace utilizes GKE Workload Identity to assume distinct GCP IAM Service Accounts (`agent-sa-a` and `agent-sa-b`), maintaining a tight security boundary.
* **Agent Personas**: 
  * **Agent A (`python_architect_agent`)**: Recommends strictly Python/asyncio-based data streaming pipelines.
  * **Agent B (`go_architect_agent`)**: Recommends strictly Go/goroutine-based data streaming pipelines.

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

### Phase 5: GKE Namespace & Workload Identity Bindings

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
4. **Grant Vertex AI Access (`aiplatform.user`) to both IAM Service Accounts**:
   ```bash
   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user"

   gcloud projects add-iam-policy-binding $PROJECT_ID \
       --member="serviceAccount:agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/aiplatform.user"
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

Before deploying, update your Kubernetes deployment files with the new values.

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

### Phase 9: Teardown & Cleanup (Optional)
To completely tear down your GKE workloads, namespaces, Workload Identity bindings, and GCP Service Accounts, run the cleanup script:

```bash
chmod +x cleanup.sh
./cleanup.sh
```

