# TaskFlow Docker Management
.PHONY: help build run run-dev stop clean logs shell test

# Default target
help:
	@echo "TaskFlow Docker Management"
	@echo "=========================="
	@echo "Available commands:"
	@echo "  build     - Build the Docker image"
	@echo "  run       - Run the application in production mode"
	@echo "  run-dev   - Run the application in development mode"
	@echo "  stop      - Stop all containers"
	@echo "  clean     - Stop containers and remove images"
	@echo "  logs      - Show application logs"
	@echo "  shell     - Get shell access to running container"
	@echo "  test      - Run tests in container"

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