# TaskFlow Management
.PHONY: help build run run-dev stop clean logs shell test k8s-setup k8s-deploy k8s-status k8s-logs k8s-clean helm-install helm-upgrade helm-uninstall helm-test ci-test ci-validate

# Default target
help:
	@echo "TaskFlow Management"
	@echo "=================="
	@echo "Docker commands:"
	@echo "  build        - Build the Docker image"
	@echo "  run          - Run the application in production mode"
	@echo "  run-dev      - Run the application in development mode"
	@echo "  stop         - Stop all containers"
	@echo "  clean        - Stop containers and remove images"
	@echo "  logs         - Show application logs"
	@echo "  shell        - Get shell access to running container"
	@echo "  test         - Run tests in container"
	@echo ""
	@echo "Kubernetes commands:"
	@echo "  k8s-setup    - Set up K3s cluster and deploy application"
	@echo "  k8s-deploy   - Deploy to existing cluster (dev)"
	@echo "  k8s-status   - Show Kubernetes deployment status"
	@echo "  k8s-logs     - Show Kubernetes application logs"
	@echo "  k8s-clean    - Delete K3s cluster"
	@echo ""
	@echo "Helm commands:"
	@echo "  helm-install - Install with Helm (dev environment)"
	@echo "  helm-upgrade - Upgrade Helm release"
	@echo "  helm-uninstall - Uninstall Helm release"
	@echo "  helm-test    - Test and validate Helm chart"
	@echo ""
	@echo "CI/CD commands:"
	@echo "  ci-test      - Run all CI checks locally"
	@echo "  ci-validate  - Validate CI/CD pipeline configuration"

# Build the Docker image
build:
	docker-compose build

# Run in production mode
run:
	docker-compose up -d

# Run in development mode with hot reload
run-dev:
	docker-compose -f docker-compose.dev.yml up

# Stop all containers
stop:
	docker-compose down
	docker-compose -f docker-compose.dev.yml down

# Clean up containers and images
clean: stop
	docker-compose down -v --rmi all
	docker-compose -f docker-compose.dev.yml down -v --rmi all

# Show logs
logs:
	docker-compose logs -f taskflow-app

# Get shell access
shell:
	docker-compose exec taskflow-app /bin/bash

# Run tests
test:
	docker-compose exec taskflow-app python -m pytest app/tests/

# Health check
health:
	curl -f http://localhost:8000/docs && echo "✅ Application is healthy"

# Kubernetes commands
k8s-setup:
	./setup-k3s.sh

k8s-deploy:
	docker build -t taskflow:latest .
	k3d image import taskflow:latest --cluster taskflow
	kubectl apply -k k8s/overlays/dev/

k8s-status:
	kubectl get all -n taskflow

k8s-logs:
	kubectl logs -f deployment/taskflow-app -n taskflow

k8s-clean:
	k3d cluster delete taskflow

# Port forward for local access
k8s-port-forward:
	kubectl port-forward service/taskflow-service 8000:80 -n taskflow

# Helm commands
helm-install:
	docker build -t taskflow:latest .
	k3d image import taskflow:latest --cluster taskflow
	helm install taskflow ./helm/taskflow --namespace taskflow --create-namespace -f helm/taskflow/values-dev.yaml

helm-upgrade:
	docker build -t taskflow:latest .
	k3d image import taskflow:latest --cluster taskflow
	helm upgrade taskflow ./helm/taskflow --namespace taskflow -f helm/taskflow/values-dev.yaml

helm-uninstall:
	helm uninstall taskflow --namespace taskflow

helm-test:
	helm lint ./helm/taskflow
	helm template taskflow ./helm/taskflow -f helm/taskflow/values-dev.yaml > /tmp/helm-output.yaml
	echo "✅ Helm chart validation complete. Output saved to /tmp/helm-output.yaml"

# Helm production deployment
helm-install-prod:
	helm install taskflow ./helm/taskflow --namespace taskflow --create-namespace -f helm/taskflow/values-prod.yaml

helm-upgrade-prod:
	helm upgrade taskflow ./helm/taskflow --namespace taskflow -f helm/taskflow/values-prod.yaml

# CI/CD commands
ci-test:
	@echo "Running local CI checks..."
	python3 -m pip install --upgrade pip
	pip3 install -r requirements.txt
	black --check app/ || (echo "Run 'black app/' to fix formatting" && exit 1)
	isort --check-only app/ || (echo "Run 'isort app/' to fix imports" && exit 1)
	flake8 app/
	cd app && python3 -m pytest tests/ -v --cov=. --cov-report=term-missing
	bandit -r app/ -ll || echo "Security warnings found"
	safety check || echo "Dependency vulnerabilities found"

ci-validate:
	./validate-cicd.sh

# Format code
format:
	black app/
	isort app/

# Security scan
security-scan:
	bandit -r app/ -f json -o security-report.json
	safety check --json --output safety-report.json
	echo "Security reports generated: security-report.json, safety-report.json"