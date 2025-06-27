#!/bin/bash

echo "🧪 Testing Kubernetes Manifests"
echo "==============================="

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl to test manifests."
    echo "   brew install kubectl"
    exit 1
fi

echo "1. Validating Kubernetes manifests..."

# Function to validate YAML
validate_yaml() {
    local file="$1"
    echo "  Validating $file..."
    
    if kubectl apply --dry-run=client -f "$file" > /dev/null 2>&1; then
        echo "    ✅ $file is valid"
    else
        echo "    ❌ $file has validation errors:"
        kubectl apply --dry-run=client -f "$file"
        return 1
    fi
}

# Validate base manifests
echo ""
echo "Testing base manifests:"
for file in k8s/base/*.yaml; do
    if [[ -f "$file" ]]; then
        validate_yaml "$file"
    fi
done

echo ""
echo "2. Testing Kustomize builds..."

# Test kustomize builds
echo ""
echo "Testing development overlay:"
if kubectl kustomize k8s/overlays/dev/ > /dev/null 2>&1; then
    echo "  ✅ Development overlay builds successfully"
    echo "  Generated resources:"
    kubectl kustomize k8s/overlays/dev/ | grep "^kind:" | sort | uniq -c
else
    echo "  ❌ Development overlay has errors"
    kubectl kustomize k8s/overlays/dev/
fi

echo ""
echo "Testing production overlay:"
if kubectl kustomize k8s/overlays/prod/ > /dev/null 2>&1; then
    echo "  ✅ Production overlay builds successfully"
    echo "  Generated resources:"
    kubectl kustomize k8s/overlays/prod/ | grep "^kind:" | sort | uniq -c
else
    echo "  ❌ Production overlay has errors"
    kubectl kustomize k8s/overlays/prod/
fi

echo ""
echo "3. Checking Docker image requirements..."
if docker images | grep -q "taskflow"; then
    echo "  ✅ TaskFlow Docker image exists"
else
    echo "  ⚠️  TaskFlow Docker image not found"
    echo "     Run 'docker build -t taskflow:latest .' to build it"
fi

echo ""
echo "🎉 Kubernetes manifest validation complete!"
echo ""
echo "📝 Next steps:"
echo "  1. Install k3d: brew install k3d"
echo "  2. Run setup: ./setup-k3s.sh"
echo "  3. Or use Make: make k8s-setup"
echo ""
echo "🔧 Manual deployment (if cluster exists):"
echo "  kubectl apply -k k8s/overlays/dev/"
echo "  kubectl get pods -n taskflow -w"