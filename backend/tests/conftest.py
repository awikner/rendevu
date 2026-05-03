import os
import pytest
from dotenv import load_dotenv
from httpx import AsyncClient, ASGITransport

# Load real API keys from .env before any test runs
load_dotenv()

# Override CLIENT_API_TOKEN with a known test value so the auth middleware
# accepts requests from the test client
_TEST_TOKEN = "test-integration-token"
os.environ["CLIENT_API_TOKEN"] = _TEST_TOKEN


@pytest.fixture
async def client():
    """FastAPI test client pre-loaded with the auth token."""
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Token": _TEST_TOKEN},
    ) as c:
        yield c


@pytest.fixture
async def client_no_token():
    """FastAPI test client with no auth token (for 401 tests)."""
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
