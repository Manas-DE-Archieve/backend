import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    # Register
    res = await client.post("/api/auth/register", json={"email": "test@example.com", "password": "password123"})
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "test@example.com"
    assert data["role"] == "user"

    # Duplicate registration should fail
    res2 = await client.post("/api/auth/register", json={"email": "test@example.com", "password": "password123"})
    assert res2.status_code == 400

    # Login
    res3 = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    assert res3.status_code == 200
    tokens = res3.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_invalid_login(client: AsyncClient):
    res = await client.post("/api/auth/login", json={"email": "nobody@x.com", "password": "wrong"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient):
    await client.post("/api/auth/register", json={"email": "me@example.com", "password": "pass"})
    login = await client.post("/api/auth/login", json={"email": "me@example.com", "password": "pass"})
    token = login.json()["access_token"]

    res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    await client.post("/api/auth/register", json={"email": "refresh@example.com", "password": "pass"})
    login = await client.post("/api/auth/login", json={"email": "refresh@example.com", "password": "pass"})
    refresh_token = login.json()["refresh_token"]

    res = await client.post("/api/auth/refresh", params={"token": refresh_token})
    assert res.status_code == 200
    assert "access_token" in res.json()
