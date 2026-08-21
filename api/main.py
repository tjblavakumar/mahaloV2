from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import admin, chat, projects
from backend.config import settings
from backend.utils.bootstrap import ensure_default_project


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure default project exists
    ensure_default_project()
    yield
    # Shutdown (if needed)


app = FastAPI(title="MAHALO Main API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(projects.router)


@app.get("/")
def root():
    return {
        "service": "MAHALO Main API",
        "version": "1.0.0",
        "status": "running",
        "port": settings.MAIN_API_PORT,
        "docs": f"http://localhost:{settings.MAIN_API_PORT}/docs",
        "frontend": f"http://localhost:{settings.FRONTEND_PORT}",
    }


@app.get("/health")
def health():
    return {"status": "healthy", "service": "main-api"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=settings.MAIN_API_PORT, reload=True)
