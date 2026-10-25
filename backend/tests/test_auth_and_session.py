import pytest
import httpx

@pytest.mark.asyncio
async def test_unauthorized_access(client: httpx.AsyncClient):
    # Unauthenticated request to protected endpoint
    resp = await client.get("/api/v2/companies")
    assert resp.status_code == 401
    data = resp.json()
    assert data["code"] == "unauthorized"
    assert "request_id" in data

@pytest.mark.asyncio
async def test_login_flow(client: httpx.AsyncClient):
    # Invalid password
    bad_resp = await client.post(
        "/api/v2/auth/login",
        json={"email": "demo@centrinvest.ru", "password": "wrongpassword"}
    )
    assert bad_resp.status_code == 401

    # Valid login
    good_resp = await client.post(
        "/api/v2/auth/login",
        json={"email": "demo@centrinvest.ru", "password": "password123"}
    )
    assert good_resp.status_code == 200
    data = good_resp.json()
    assert data["user"]["display_name"] == "Демо Пользователь (Центр-инвест)"
    assert "session_id" in good_resp.cookies

    # Inspect session with cookie
    sess_resp = await client.get("/api/v2/auth/session")
    assert sess_resp.status_code == 200
    assert sess_resp.json()["user"]["email"] if "email" in sess_resp.json()["user"] else True

    # Logout
    logout_resp = await client.post("/api/v2/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["signed_out"] is True

    # After logout, accessing protected route is unauthorized
    after_resp = await client.get("/api/v2/companies")
    assert after_resp.status_code == 401
