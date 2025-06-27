#!/bin/bash

echo "🚀 Setting up K3s Kubernetes Cluster for TaskFlow"
echo "=================================================="

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
  echo "❌ This script is designed for macOS. For other platforms, please install K3s manually."
  exit 1
fi

# Install K3s using k3d (for local development on macOS)
echo "1. Installing k3d (K3s in Docker)..."
if ! command -v k3d &> /dev/null; then
    if command -v brew &> /dev/null; then
        brew install k3d
    else
        echo "❌ Homebrew not found. Please install k3d manually:"
        echo "   curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash"
        exit 1
    fi
fi

# Check if kubectl is installed
echo "2. Checking kubectl installation..."
if ! command -v kubectl &> /dev/null; then
    echo "Installing kubectl..."
    if command -v brew &> /dev/null; then
        brew install kubectl
    else
        echo "❌ Please install kubectl manually"
        exit 1
    fi
fi

# Create K3s cluster
echo "3. Creating K3s cluster 'taskflow'..."
k3d cluster create taskflow \
  --port "8080:80@loadbalancer" \
  --port "8443:443@loadbalancer" \
  --servers 1 \
  --agents 2 \
  --registry-create taskflow-registry:0.0.0.0:5000

# Wait for cluster to be ready
echo "4. Waiting for cluster to be ready..."
kubectl wait --for=condition=ready nodes --all --timeout=120s

# Create local storage class
echo "5. Setting up local storage..."
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-storage
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
EOF

# Build and load Docker image into k3d
echo "6. Building and loading Docker image..."
docker build -t taskflow:latest .
k3d image import taskflow:latest --cluster taskflow

# Apply Kubernetes manifests
echo "7. Deploying TaskFlow to Kubernetes..."
kubectl apply -k k8s/overlays/dev/

# Wait for deployment
echo "8. Waiting for deployment to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/taskflow-app -n taskflow

# Get cluster info
echo ""
echo "🎉 K3s cluster setup complete!"
echo "=============================="
echo ""
echo "Cluster Info:"
kubectl cluster-info
echo ""
echo "Nodes:"
kubectl get nodes
echo ""
echo "TaskFlow Application Status:"
kubectl get all -n taskflow
echo ""
echo "📝 Access Instructions:"
echo "  1. Add to /etc/hosts: 127.0.0.1 taskflow.local"
echo "  2. Access app: http://taskflow.local:8080"
echo "  3. Monitor: kubectl get pods -n taskflow -w"
echo ""
echo "🔧 Useful Commands:"
echo "  kubectl logs -f deployment/taskflow-app -n taskflow"
echo "  kubectl describe pod -n taskflow"
echo "  kubectl port-forward service/taskflow-service 8000:80 -n taskflow"
echo ""
echo "🗑️  To cleanup:"
echo "  k3d cluster delete taskflow"