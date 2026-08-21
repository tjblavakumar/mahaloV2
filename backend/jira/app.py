from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.database import init_db
from backend.jira.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (if needed)


app = FastAPI(title="MAHALO JIRA Mock API", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "jira-api"}
