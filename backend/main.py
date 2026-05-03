import os
from fastapi import FastAPI, Security, HTTPException, Depends
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routers import flights, lodging

load_dotenv()

app = FastAPI(title="Rendevu API", version="0.1.0")

_pages_origin = os.getenv("GITHUB_PAGES_ORIGIN", "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_pages_origin] if _pages_origin else [],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Token"],
)

_api_key_header = APIKeyHeader(name="X-API-Token", auto_error=False)


async def _require_token(key: str = Security(_api_key_header)) -> None:
    expected = os.getenv("CLIENT_API_TOKEN")
    if not expected or key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


app.include_router(flights.router, prefix="/api", dependencies=[Depends(_require_token)])
app.include_router(lodging.router, prefix="/api", dependencies=[Depends(_require_token)])


@app.get("/health")
async def health():
    return {"status": "ok"}
