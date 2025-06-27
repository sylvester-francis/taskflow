#!/bin/bash

echo "🧪 Validating TaskFlow Helm Chart Structure"
echo "==========================================="

echo "1. Checking chart structure..."

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
    "helm/taskflow/templates/namespace.yaml"
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
echo "2. Validating YAML syntax..."

# Function to validate YAML syntax
validate_yaml_syntax() {
    local file="$1"
    if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
        echo "    ✅ $file has valid YAML syntax"
    else
        echo "    ❌ $file has YAML syntax errors"
        return 1
    fi
}

# Check if Python with PyYAML is available
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "  ⚠️  Python with PyYAML not available, skipping YAML validation"
    echo "     Install with: pip3 install pyyaml"
else
    error_count=0
    for file in helm/taskflow/*.yaml; do
        if [[ -f "$file" ]]; then
            validate_yaml_syntax "$file" || ((error_count++))
        fi
    done
    
    if [[ $error_count -eq 0 ]]; then
        echo "  ✅ All YAML files have valid syntax"
    else
        echo "  ❌ Found $error_count YAML syntax errors"
        missing_files=$((missing_files + error_count))
    fi
fi

echo ""
echo "3. Checking Chart.yaml metadata..."

if [[ -f "helm/taskflow/Chart.yaml" ]]; then
    if grep -q "apiVersion: v2" helm/taskflow/Chart.yaml; then
        echo "  ✅ Chart uses Helm v3 API version"
    else
        echo "  ⚠️  Chart might be using older API version"
    fi
    
    if grep -q "type: application" helm/taskflow/Chart.yaml; then
        echo "  ✅ Chart type correctly set to application"
    else
        echo "  ⚠️  Chart type not specified or incorrect"
    fi
    
    chart_version=$(grep "version:" helm/taskflow/Chart.yaml | head -1 | awk '{print $2}')
    app_version=$(grep "appVersion:" helm/taskflow/Chart.yaml | awk '{print $2}' | tr -d '"')
    echo "  📋 Chart version: $chart_version"
    echo "  📋 App version: $app_version"
fi

echo ""
echo "4. Checking values file structure..."

if [[ -f "helm/taskflow/values.yaml" ]]; then
    if grep -q "replicaCount:" helm/taskflow/values.yaml; then
        echo "  ✅ Replica count configuration found"
    fi
    
    if grep -q "image:" helm/taskflow/values.yaml; then
        echo "  ✅ Image configuration found"
    fi
    
    if grep -q "ingress:" helm/taskflow/values.yaml; then
        echo "  ✅ Ingress configuration found"
    fi
    
    if grep -q "autoscaling:" helm/taskflow/values.yaml; then
        echo "  ✅ Autoscaling configuration found"
    fi
    
    if grep -q "environments:" helm/taskflow/values.yaml; then
        echo "  ✅ Environment-specific configurations found"
    fi
fi

echo ""
echo "5. Checking environment-specific values..."

environments=("dev" "staging" "prod")
for env in "${environments[@]}"; do
    file="helm/taskflow/values-$env.yaml"
    if [[ -f "$file" ]]; then
        echo "  ✅ $env environment values file exists"
        if grep -q "environment.*$env" "$file"; then
            echo "    ✅ Environment correctly set to $env"
        fi
    else
        echo "  ❌ $env environment values file missing"
        ((missing_files++))
    fi
done

echo ""
if [[ $missing_files -eq 0 ]]; then
    echo "🎉 Helm chart structure validation successful!"
    echo ""
    echo "📝 Chart ready for deployment!"
    echo "  Next steps:"
    echo "    1. Install Helm: brew install helm"
    echo "    2. Test chart: helm lint ./helm/taskflow"
    echo "    3. Template test: helm template taskflow ./helm/taskflow"
    echo "    4. Deploy: make helm-install"
    echo ""
    echo "🔧 Available environments:"
    echo "  Development: -f helm/taskflow/values-dev.yaml"
    echo "  Staging:     -f helm/taskflow/values-staging.yaml" 
    echo "  Production:  -f helm/taskflow/values-prod.yaml"
else
    echo "❌ Found $missing_files validation errors"
    echo "   Please fix the errors before deploying"
    exit 1
fi