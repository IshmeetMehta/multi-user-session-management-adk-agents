#!/usr/bin/env bash

# =====================================================================
# STANDARD CLEANUP & TEARDOWN SCRIPT (memory-bank-implementation)
# =====================================================================
# This script deletes all GKE workloads, namespaces, Workload Identity
# bindings, and GCP IAM Service Accounts created during standard deployment.
# =====================================================================

set -eo pipefail

export PROJECT_ID="GCP_PROJECT_ID"
export REGION="us-central1"
export CLUSTER_NAME="agent-memory-cluster"

echo "⏳ Starting environment teardown..."

# 1. Delete Deployed Kubernetes Workloads (if any)
echo "🧹 Deleting Kubernetes deployments..."
kubectl delete -f deployment/agent-a.deployment.yaml --ignore-not-found=true || true
kubectl delete -f deployment/agent-b.deployment.yaml --ignore-not-found=true || true

# 2. Delete Kubernetes Namespaces
echo "🧹 Deleting Kubernetes namespaces (namespace-a, namespace-b)..."
kubectl delete -f create-namespace.yaml --ignore-not-found=true || true
kubectl delete ns namespace-a namespace-b --ignore-not-found=true || true

# 3. Revoke IAM Policy Bindings
echo "🔓 Revoking GCP IAM policy bindings..."

# Revoke project-wide Vertex AI permissions
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

# 4. Delete GCP IAM Service Accounts
echo "🧹 Deleting GCP Service Accounts..."
gcloud iam service-accounts delete "agent-sa-a@$PROJECT_ID.iam.gserviceaccount.com" --quiet || true
gcloud iam service-accounts delete "agent-sa-b@$PROJECT_ID.iam.gserviceaccount.com" --quiet || true

echo "✅ [Teardown Complete] Standard resources successfully cleaned up!"
