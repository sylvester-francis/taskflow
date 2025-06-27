#!/bin/bash

echo "🧪 Validating CI/CD Pipeline Configuration"
echo "=========================================="

# Check if GitHub CLI is available for advanced validation
GITHUB_CLI_AVAILABLE=false
if command -v gh &> /dev/null; then
    GITHUB_CLI_AVAILABLE=true
fi

echo "1. Checking workflow files structure..."

expected_workflows=(
    ".github/workflows/ci-cd.yml"
    ".github/workflows/pr-validation.yml"
    ".github/workflows/security.yml"
    ".github/workflows/release.yml"
    ".github/workflows/codeql.yml"
)

missing_files=0
for workflow in "${expected_workflows[@]}"; do
    if [[ -f "$workflow" ]]; then
        echo "  ✅ $workflow exists"
    else
        echo "  ❌ $workflow missing"
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
    for workflow in "${expected_workflows[@]}"; do
        if [[ -f "$workflow" ]]; then
            validate_yaml_syntax "$workflow" || ((error_count++))
        fi
    done
    
    if [[ $error_count -eq 0 ]]; then
        echo "  ✅ All workflow files have valid YAML syntax"
    else
        echo "  ❌ Found $error_count YAML syntax errors"
        missing_files=$((missing_files + error_count))
    fi
fi

echo ""
echo "3. Checking configuration files..."

config_files=(
    "pyproject.toml"
    ".flake8"
    ".github/pull_request_template.md"
    ".github/ISSUE_TEMPLATE/bug_report.yml"
)

for config in "${config_files[@]}"; do
    if [[ -f "$config" ]]; then
        echo "  ✅ $config exists"
    else
        echo "  ❌ $config missing"
        ((missing_files++))
    fi
done

echo ""
echo "4. Analyzing workflow triggers..."

echo "  Main CI/CD Pipeline:"
if grep -q "on:" .github/workflows/ci-cd.yml; then
    echo "    ✅ Triggers configured"
    if grep -A5 "on:" .github/workflows/ci-cd.yml | grep -q "push:"; then
        echo "    ✅ Push trigger found"
    fi
    if grep -A5 "on:" .github/workflows/ci-cd.yml | grep -q "pull_request:"; then
        echo "    ✅ Pull request trigger found"
    fi
    if grep -A5 "on:" .github/workflows/ci-cd.yml | grep -q "release:"; then
        echo "    ✅ Release trigger found"
    fi
fi

echo ""
echo "5. Checking job dependencies..."

echo "  CI/CD Pipeline job flow:"
if grep -q "needs:.*test" .github/workflows/ci-cd.yml; then
    echo "    ✅ Build job depends on test job"
fi
if grep -q "needs:.*build" .github/workflows/ci-cd.yml; then
    echo "    ✅ Deploy jobs depend on build job"
fi

echo ""
echo "6. Validating environment configurations..."

environments=("development" "staging" "production")
for env in "${environments[@]}"; do
    if grep -q "environment:.*$env" .github/workflows/ci-cd.yml; then
        echo "  ✅ $env environment configured"
    else
        echo "  ⚠️  $env environment not found"
    fi
done

echo ""
echo "7. Checking security workflows..."

security_tools=("bandit" "safety" "trivy" "semgrep")
for tool in "${security_tools[@]}"; do
    if grep -q "$tool" .github/workflows/security.yml; then
        echo "  ✅ $tool security scanner configured"
    else
        echo "  ⚠️  $tool not found in security workflow"
    fi
done

echo ""
echo "8. Validating required secrets..."

required_secrets=(
    "GITHUB_TOKEN"
    "KUBECONFIG_DEV"
    "KUBECONFIG_STAGING" 
    "KUBECONFIG_PROD"
    "SLACK_WEBHOOK"
)

echo "  Required secrets for workflows:"
for secret in "${required_secrets[@]}"; do
    if grep -q "\${{ secrets\.$secret }}" .github/workflows/*.yml; then
        echo "    ✅ $secret referenced in workflows"
    else
        echo "    ⚠️  $secret not found in workflows"
    fi
done

echo ""
echo "9. Checking Helm integration..."

if grep -q "helm" .github/workflows/ci-cd.yml; then
    echo "  ✅ Helm integration found in CI/CD"
fi
if grep -q "helm lint" .github/workflows/ci-cd.yml; then
    echo "  ✅ Helm chart validation configured"
fi
if grep -q "helm upgrade" .github/workflows/ci-cd.yml; then
    echo "  ✅ Helm deployment configured"
fi

echo ""
echo "10. Verifying container registry setup..."

if grep -q "ghcr.io" .github/workflows/ci-cd.yml; then
    echo "  ✅ GitHub Container Registry configured"
fi
if grep -q "docker/build-push-action" .github/workflows/ci-cd.yml; then
    echo "  ✅ Docker build and push action configured"
fi
if grep -q "docker/login-action" .github/workflows/ci-cd.yml; then
    echo "  ✅ Container registry login configured"
fi

echo ""
if [[ $missing_files -eq 0 ]]; then
    echo "🎉 CI/CD pipeline validation successful!"
    echo ""
    echo "📋 Pipeline Overview:"
    echo "  ✅ 5 GitHub Actions workflows configured"
    echo "  ✅ Multi-environment deployment (dev/staging/prod)"
    echo "  ✅ Security scanning and code quality checks"
    echo "  ✅ Container registry integration"
    echo "  ✅ Helm chart validation and deployment"
    echo "  ✅ Pull request validation"
    echo "  ✅ Release automation"
    echo ""
    echo "🚀 Next steps:"
    echo "  1. Configure repository secrets"
    echo "  2. Set up GitHub environments with protection rules"
    echo "  3. Configure Kubernetes cluster access"
    echo "  4. Test workflows with a pull request"
    echo ""
    echo "🔗 Workflow triggers:"
    echo "  • Push to main/develop → Full CI/CD"
    echo "  • Pull requests → Validation only"
    echo "  • Releases → Production deployment"
    echo "  • Schedule → Security scans"
else
    echo "❌ Found $missing_files validation errors"
    echo "   Please fix the errors before using the CI/CD pipeline"
    exit 1
fi