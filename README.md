# TaskFlow - Secure Task Tracking Application

A secure, containerized task-tracking application built with FastAPI, HTMX, and deployed on Kubernetes.

## 🚀 Quick Start

### Local Development

1. **Clone and setup virtual environment:**

   ```bash
   git clone <repo-url>
   cd taskflow
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Run the application:**

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Access the application:**
   - Main app: <http://localhost:8000>
   - API docs: <http://localhost:8000/docs>

### Docker Development

1. **Prerequisites:**
   - Docker Desktop installed and running
   - Docker Compose v2+

2. **Development mode (with hot reload):**

   ```bash
   make run-dev
   # OR
   docker-compose -f docker-compose.dev.yml up
   ```

3. **Production mode:**

   ```bash
   make build
   make run
   # OR
   docker-compose build
   docker-compose up -d
   ```

4. **Available Make commands:**

   ```bash
   make help          # Show all available commands
   make build         # Build Docker image
   make run           # Run in production mode
   make run-dev       # Run in development mode
   make stop          # Stop containers
   make clean         # Clean up containers and images
   make logs          # Show application logs
   make shell         # Get shell access
   make test          # Run tests
   make health        # Check application health
   ```

## 🏗️ Architecture

### Application Structure

```
taskflow/
├── app/
│   ├── backend/          # FastAPI backend
│   │   ├── models.py     # SQLAlchemy models
│   │   ├── routes.py     # API routes
│   │   ├── auth.py       # JWT authentication
│   │   └── database.py   # Database configuration
│   ├── frontend/         # HTMX + Bootstrap frontend
│   │   ├── templates/    # Jinja2 templates
│   │   └── static/       # CSS, JS assets
│   ├── tests/            # Test suite
│   └── main.py           # FastAPI application
├── Dockerfile            # Multi-stage container build
├── docker-compose.yml    # Production container setup
├── docker-compose.dev.yml # Development setup
└── requirements.txt      # Python dependencies
```

### Security Features

- **Authentication**: JWT tokens with bcrypt password hashing
- **Container Security**: Non-root user, minimal attack surface
- **Input Validation**: Pydantic models for request validation
- **HTTPS Ready**: Configured for TLS termination at load balancer

## 🐳 Container Features

### Multi-stage Dockerfile

- **Builder stage**: Installs dependencies and builds application
- **Production stage**: Minimal runtime image with security hardening
- **Non-root user**: Application runs as `taskflow` user
- **Health checks**: Built-in container health monitoring

### Docker Compose Services

- **taskflow-app**: Main application container
- **taskflow-backup**: Automated database backup service
- **Volume persistence**: Data stored in Docker volumes
- **Network isolation**: Custom bridge network

## 🔧 Configuration

### Environment Variables

- `DATABASE_PATH`: Path to SQLite database file (default: `./taskflow.db`)
- `PYTHONPATH`: Python module search path (default: `/app`)
- `ENVIRONMENT`: Application environment (development/production)

### Database

- **Development**: SQLite with local file storage
- **Production**: SQLite with volume-mounted persistence
- **Backup**: Automated daily backups with 7-day retention

## 🧪 Testing

```bash
# Local testing
python -m pytest app/tests/

# Container testing
make test
```

## 📝 Development Notes

### Phase 2 Complete ✅

- FastAPI backend with CRUD operations
- HTMX frontend with Bootstrap styling
- JWT authentication system
- SQLite database with SQLAlchemy ORM
- Containerized deployment ready

### Next Phases

- [ ] Kubernetes deployment (K3s/Minikube)
- [ ] Helm charts for environment management
- [ ] CI/CD pipeline with GitHub Actions
- [ ] Security scanning (SAST/DAST/Container scanning)
- [ ] Monitoring and observability stack

## 🔒 Security Considerations

- Change `SECRET_KEY` in production
- Use environment variables for sensitive configuration
- Enable HTTPS in production
- Regular security updates for base images
- Database backups and disaster recovery

## 📚 API Documentation

Once running, visit `/docs` for interactive API documentation powered by FastAPI's automatic OpenAPI generation.
