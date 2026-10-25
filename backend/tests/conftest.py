import uuid
import pytest
import pytest_asyncio
import httpx
from src.main import app
from src.database import init_db, async_session_factory, engine
from src.services.auth_service import AuthService
from src.models.entities import Company, CompanyMembership
from sqlalchemy import select

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    await init_db()
    async with async_session_factory() as db:
        await AuthService.get_or_create_demo_user(db)

@pytest_asyncio.fixture(autouse=True)
async def db_savepoint_isolation():
    async with engine.connect() as conn:
        trans = await conn.begin()
        async_session_factory.configure(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield conn
        finally:
            if trans.is_active:
                await trans.rollback()
            async_session_factory.configure(bind=engine, join_transaction_mode="conditional_savepoint")

@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def auth_client(client: httpx.AsyncClient):
    login_resp = await client.post(
        "/api/v2/auth/login",
        json={"email": "demo@centrinvest.ru", "password": "password123"}
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    return client

@pytest_asyncio.fixture
async def fresh_company_id(auth_client: httpx.AsyncClient):
    resp = await auth_client.post(
        "/api/v2/companies",
        json={
            "name": f"Компания {uuid.uuid4().hex[:8]}",
            "business_type": "Грузоперевозки",
            "timezone": "Europe/Moscow"
        }
    )
    assert resp.status_code == 201
    return resp.json()["id"]
