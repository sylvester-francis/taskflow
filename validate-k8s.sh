#!/bin/bash

echo "🧪 Validating Kubernetes YAML Syntax"
echo "===================================="

# Function to validate YAML syntax
validate_yaml_syntax() {
    local file="$1"
    echo "  Checking $file..."
    
    if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
        echo "    ✅ $file has valid YAML syntax"
    else
        echo "    ❌ $file has YAML syntax errors"
        return 1
    fi
}

# Check if Python with PyYAML is available
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "❌ Python with PyYAML not available. Installing..."
    pip3 install pyyaml 2>/dev/null || {
        echo "❌ Cannot install PyYAML. Please install manually: pip3 install pyyaml"
        exit 1
    }
fi

echo "1. Validating YAML syntax in base manifests..."
error_count=0

for file in k8s/base/*.yaml; do
    if [[ -f "$file" && "$file" != *"kustomization.yaml" ]]; then
        validate_yaml_syntax "$file" || ((error_count++))
    fi
done

echo ""
echo "2. Testing Kustomize build (offline)..."

if command -v kustomize &> /dev/null; then
    echo "  Testing development overlay..."
    if kustomize build k8s/overlays/dev/ > /tmp/dev-output.yaml 2>/dev/null; then
        echo "    ✅ Development overlay builds successfully"
        resource_count=$(grep -c "^kind:" /tmp/dev-output.yaml)
        echo "    📊 Generated $resource_count resources"
    else
        echo "    ❌ Development overlay build failed"
        ((error_count++))
    fi
    
    echo "  Testing production overlay..."
    if kustomize build k8s/overlays/prod/ > /tmp/prod-output.yaml 2>/dev/null; then
        echo "    ✅ Production overlay builds successfully"
        resource_count=$(grep -c "^kind:" /tmp/prod-output.yaml)
        echo "    📊 Generated $resource_count resources"
    else
        echo "    ❌ Production overlay build failed"
        ((error_count++))
    fi
else
    echo "  ⚠️  kustomize not found, skipping build test"
    echo "     Install with: brew install kustomize"
fi

echo ""
echo "3. Checking file structure..."
expected_files=(
    "k8s/base/namespace.yaml"
    "k8s/base/configmap.yaml"
    "k8s/base/secret.yaml"
    "k8s/base/deployment.yaml"
    "k8s/base/service.yaml"
    "k8s/base/ingress.yaml"
    "k8s/base/persistent-volume.yaml"
    "k8s/overlays/dev/kustomization.yaml"
    "k8s/overlays/prod/kustomization.yaml"
)

for file in "${expected_files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "  ✅ $file exists"
    else
        echo "  ❌ $file missing"
        ((error_count++))
    fi
done

echo ""
if [[ $error_count -eq 0 ]]; then
    echo "🎉 All validations passed!"
    echo ""
    echo "📝 Ready for deployment!"
    echo "  Next steps:"
    echo "    1. Install k3d: brew install k3d"
    echo "    2. Run: make k8s-setup"
    echo "    3. Access: http://taskflow.local:8080"
else
    echo "❌ Found $error_count validation errors"
    echo "   Please fix the errors before deploying"
fi

# Cleanup
rm -f /tmp/dev-output.yaml /tmp/prod-output.yaml