from datetime import timedelta
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.backend.auth import (
    authenticate_user,
    create_access_token,
    get_current_user_from_cookie,
)
from app.backend.database import create_tables, get_db
from app.backend.models import Task, User
from app.backend.routes import router

app = FastAPI(title="TaskFlow", description="Secure Task Tracking Application")

# Get the directory where this main.py file is located
BASE_DIR = Path(__file__).parent

# Set up template and static directories
templates_dir = BASE_DIR / "frontend" / "templates"
static_dir = BASE_DIR / "frontend" / "static"

templates = Jinja2Templates(directory=str(templates_dir))

# Only mount static files if the directory exists
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(router, prefix="/api", tags=["api"])

create_tables()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.post("/htmx/register")
async def htmx_register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.backend.auth import get_password_hash, get_user

    # Check if user already exists
    db_user = get_user(db, username=username)
    if db_user:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": "Username already registered"},
        )

    # Create new user
    hashed_password = get_password_hash(password)
    db_user = User(username=username, email=email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return templates.TemplateResponse(
        "partials/login_success.html",
        {
            "request": request,
            "username": db_user.username,
            "message": "Account created successfully! You can now login.",
        },
    )


@app.post("/htmx/login")
async def htmx_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "partials/error.html", {"request": request, "error": "Invalid credentials"}
        )

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    response = templates.TemplateResponse(
        "partials/login_success.html", {"request": request, "username": user.username}
    )
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return response


@app.post("/htmx/tasks")
async def htmx_create_task(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    task = Task(
        title=title,
        description=description,
        priority=priority,
        owner_id=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return templates.TemplateResponse(
        "partials/task_row.html", {"request": request, "task": task}
    )


@app.get("/htmx/tasks")
async def htmx_get_tasks(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    tasks = db.query(Task).filter(Task.owner_id == current_user.id).all()
    return templates.TemplateResponse(
        "partials/task_list.html", {"request": request, "tasks": tasks}
    )


@app.put("/htmx/tasks/{task_id}/toggle")
async def htmx_toggle_task(
    task_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.owner_id == current_user.id)
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.completed = not task.completed
    db.commit()
    db.refresh(task)

    return templates.TemplateResponse(
        "partials/task_row.html", {"request": request, "task": task}
    )


@app.delete("/htmx/tasks/{task_id}")
async def htmx_delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db),
):
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.owner_id == current_user.id)
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return ""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
