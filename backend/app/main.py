
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from backend.app.api.vendors import router as vendors_router
from backend.app.api.events import router as events_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.invitations import router as invitations_router


class RootResponse(BaseModel):
    app: str
    message: str
    status: str


class HealthResponse(BaseModel):
    status: str


app = FastAPI(
    title="Planova AI",
    description="AI-powered event planning and risk intelligence.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(events_router)
app.include_router(dashboard_router)
app.include_router(invitations_router)
app.include_router(vendors_router)

@app.get("/", response_model=RootResponse)
def root() -> RootResponse:
    return RootResponse(
        app="Planova AI",
        message="Every detail aligned. Every moment extraordinary.",
        status="running",
    )


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="healthy")
