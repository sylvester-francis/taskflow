#!/bin/bash

echo "🧪 Testing TaskFlow Helm Chart"
echo "=============================="

# Check if helm is available
if ! command -v helm &> /dev/null; then
    echo "❌ Helm not found. Please install Helm to test charts."
    echo "   brew install helm"
    exit 1
fi

echo "1. Linting Helm chart..."
if helm lint ./helm/taskflow; then
    echo "  ✅ Helm chart passes linting"
else
    echo "  ❌ Helm chart has linting errors"
    exit 1
fi

echo ""
echo "2. Testing chart templates..."

# Test development values
echo "  Testing development template..."
if helm template taskflow-dev ./helm/taskflow -f helm/taskflow/values-dev.yaml > /tmp/helm-dev-output.yaml 2>/dev/null; then
    echo "    ✅ Development template renders successfully"
    resource_count=$(grep -c "^kind:" /tmp/helm-dev-output.yaml)
    echo "    📊 Generated $resource_count resources"
else
    echo "    ❌ Development template rendering failed"
    helm template taskflow-dev ./helm/taskflow -f helm/taskflow/values-dev.yaml
    exit 1
fi

# Test staging values
echo "  Testing staging template..."
if helm template taskflow-staging ./helm/taskflow -f helm/taskflow/values-staging.yaml > /tmp/helm-staging-output.yaml 2>/dev/null; then
    echo "    ✅ Staging template renders successfully"
    resource_count=$(grep -c "^kind:" /tmp/helm-staging-output.yaml)
    echo "    📊 Generated $resource_count resources"
else
    echo "    ❌ Staging template rendering failed"
    exit 1
fi

# Test production values
echo "  Testing production template..."
if helm template taskflow-prod ./helm/taskflow -f helm/taskflow/values-prod.yaml > /tmp/helm-prod-output.yaml 2>/dev/null; then
    echo "    ✅ Production template renders successfully"
    resource_count=$(grep -c "^kind:" /tmp/helm-prod-output.yaml)
    echo "    📊 Generated $resource_count resources"
else
    echo "    ❌ Production template rendering failed"
    exit 1
fi

echo ""
echo "3. Validating chart structure..."

expected_files=(
    "helm/taskflow/Chart.yaml"
    "helm/taskflow/values.yaml"
    "helm/taskflow/values-dev.yaml"
    "helm/taskflow/values-staging.yaml"
    "helm/taskflow/values-prod.yaml"
    "helm/taskflow/templates/_helpers.tpl"
    "helm/taskflow/templates/deployment.yaml"
    "helm/taskflow/templates/service.yaml"
    "helm/taskflow/templates/ingress.yaml"
    "helm/taskflow/templates/configmap.yaml"
    "helm/taskflow/templates/secret.yaml"
    "helm/taskflow/templates/serviceaccount.yaml"
    "helm/taskflow/templates/persistentvolume.yaml"
    "helm/taskflow/templates/persistentvolumeclaim.yaml"
    "helm/taskflow/templates/hpa.yaml"
    "helm/taskflow/templates/NOTES.txt"
)

missing_files=0
for file in "${expected_files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "  ✅ $file exists"
    else
        echo "  ❌ $file missing"
        ((missing_files++))
    fi
done

echo ""
echo "4. Checking template features..."

# Check if HPA is disabled in dev
if grep -q "autoscaling.*enabled.*false" /tmp/helm-dev-output.yaml; then
    echo "  ✅ HPA correctly disabled in development"
else
    echo "  ⚠️  HPA configuration in development"
fi

# Check if resources are different between environments
dev_cpu_limit=$(grep -A5 "limits:" /tmp/helm-dev-output.yaml | grep "cpu:" | head -1 | awk '{print $2}')
prod_cpu_limit=$(grep -A5 "limits:" /tmp/helm-prod-output.yaml | grep "cpu:" | head -1 | awk '{print $2}')

if [[ "$dev_cpu_limit" != "$prod_cpu_limit" ]]; then
    echo "  ✅ Resource limits differ between environments (dev: $dev_cpu_limit, prod: $prod_cpu_limit)"
else
    echo "  ⚠️  Resource limits are the same across environments"
fi

echo ""
if [[ $missing_files -eq 0 ]]; then
    echo "🎉 Helm chart validation successful!"
    echo ""
    echo "📝 Ready for deployment!"
    echo "  Development: helm install taskflow ./helm/taskflow -f helm/taskflow/values-dev.yaml"
    echo "  Staging:     helm install taskflow ./helm/taskflow -f helm/taskflow/values-staging.yaml"
    echo "  Production:  helm install taskflow ./helm/taskflow -f helm/taskflow/values-prod.yaml"
    echo ""
    echo "🔧 Or use Make commands:"
    echo "  make helm-install     (development)"
    echo "  make helm-install-prod (production)"
else
    echo "❌ Found $missing_files missing files"
    echo "   Please ensure all required templates exist"
    exit 1
fi

# Cleanup
rm -f /tmp/helm-*-output.yaml