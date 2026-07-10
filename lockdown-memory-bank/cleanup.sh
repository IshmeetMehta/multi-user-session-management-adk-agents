#!/usr/bin/env bash

# =====================================================================
# LOCKDOWN CLEANUP & TEARDOWN SCRIPT (lockdown-memory-bank)
# =====================================================================
# This script deletes all GKE workloads, namespaces, Workload Identity
# bindings, GCP IAM Service Accounts, and custom conditional IAM policies.
# =====================================================================

set -eo pipefail

export PROJECT_ID="GCP_PROJECT_ID"
export REGION="us-central1"
export CLUSTER_NAME="agent-memory-cluster"

# Extract Reasoning Engine IDs
export ENGINE_ID_A="REASONING_ENGINE_ID_A"
export ENGINE_ID_B="REASONING_ENGINE_ID_B"

echo "⏳ Starting environment teardown (with secure policy removal)..."

# 1. Delete Deployed Kubernetes Workloads (if any)
echo "🧹 Deleting Kubernetes deployments..."
kubectl delete -f deployment/agent-a.deployment.yaml --ignore-not-found=true || true
kubectl delete -f deployment/agent-b.deployment.yaml --ignore-not-found=true || true

# 2. Delete Kubernetes Namespaces
echo "🧹 Deleting Kubernetes namespaces (namespace-a, namespace-b)..."
kubectl delete -f create-namespace.yaml --ignore-not-found=true || true
kubectl delete ns namespace-a namespace-b --ignore-not-found=true || true

# 3. Revoke Secure Conditional IAM Policy Bindings
echo "🔓 Removing resource-level (Layer 1) IAM conditions..."

CONDITION_EXPR_A="resource.type == 'aiplatform.googleapis.com/ReasoningEngine' && resource.name == 'projects/$PROJECT_ID/locations/$REGION/reasoningEngines/$ENGINE_ID_A'"
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user" \
    --condition="expression=${CONDITION_EXPR_A},title=RestrictToAgentAEngine,description=Only allow Agent A SA to call its own Reasoning Engine" || true

CONDITION_EXPR_B="resource.type == 'aiplatform.googleapis.com/ReasoningEngine' && resource.name == 'projects/$PROJECT_ID/locations/$REGION/reasoningEngines/$ENGINE_ID_B'"
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user" \
    --condition="expression=${CONDITION_EXPR_B},title=RestrictToAgentBEngine,description=Only allow Agent B SA to call its own Reasoning Engine" || true

echo "🔓 Removing memoryScope-level (Layer 2) IAM conditions..."

CONDITION_SCOPE_A="api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['userId'] == 'agent-a'"
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.memoryUser" \
    --condition="expression=${CONDITION_SCOPE_A},title=AgentAMemoryScopeLock,description=Only allow access to memories associated with Agent A's user scope" || true

CONDITION_SCOPE_B="api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['userId'] == 'agent-b'"
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.memoryUser" \
    --condition="expression=${CONDITION_SCOPE_B},title=AgentBMemoryScopeLock,description=Only allow access to memories associated with Agent B's user scope" || true

# 4. Revoke Standard Vertex AI permissions (if any leftover project-wide bindings exist)
echo "🔓 Removing any broad project-wide roles..."
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user" || true

gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user" || true

# Revoke Workload Identity bindings
gcloud iam service-accounts remove-iam-policy-binding "agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:$PROJECT_ID.svc.id.goog[namespace-a/agent-ksa-a]" || true

gcloud iam service-accounts remove-iam-policy-binding "agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:$PROJECT_ID.svc.id.goog[namespace-b/agent-ksa-b]" || true

# 5. Delete GCP IAM Service Accounts
echo "🧹 Deleting GCP Service Accounts..."
gcloud iam service-accounts delete "agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" --quiet || true
gcloud iam service-accounts delete "agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" --quiet || true

echo "✅ [Teardown Complete] Lockdown resources successfully cleaned up!"
