# TaskFlow Management
.PHONY: help build run run-dev stop clean logs shell test k8s-setup k8s-deploy k8s-status k8s-logs k8s-clean

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