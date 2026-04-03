import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

MOCK_EMBEDDING = [0.0] * 1536


async def get_auth_headers(client: AsyncClient, email: str = "persons_test@x.com") -> dict:
    await client.post("/api/auth/register", json={"email": email, "password": "pass"})
    res = await client.post("/api/auth/login", json={"email": email, "password": "pass"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.asyncio
@patch("app.services.embedding.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
@patch("app.services.duplicate.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
async def test_create_and_get_person(mock_dup, mock_emb, client: AsyncClient):
    headers = await get_auth_headers(client)
    payload = {
        "full_name": "Байтемиров Асан",
        "birth_year": 1899,
        "region": "Чуйская область",
        "charge": "58 статья",
        "force": True,  # skip duplicate check
    }
    res = await client.post("/api/persons", json=payload, headers=headers)
    assert res.status_code == 201
    person = res.json()
    assert person["full_name"] == "Байтемиров Асан"
    assert person["status"] == "pending"
    pid = person["id"]

    # Get by ID
    res2 = await client.get(f"/api/persons/{pid}")
    assert res2.status_code == 200
    assert res2.json()["id"] == pid


@pytest.mark.asyncio
@patch("app.services.embedding.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
@patch("app.services.duplicate.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
async def test_list_with_filters(mock_dup, mock_emb, client: AsyncClient):
    headers = await get_auth_headers(client, "list_test@x.com")
    for name in ["Алиев Марат", "Токтоматов Жакып"]:
        await client.post("/api/persons", json={"full_name": name, "region": "Ошская область", "force": True}, headers=headers)

    res = await client.get("/api/persons", params={"region": "Ошская область"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
@patch("app.services.embedding.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
@patch("app.services.duplicate.embed_text", new_callable=AsyncMock, return_value=MOCK_EMBEDDING)
async def test_update_person(mock_dup, mock_emb, client: AsyncClient):
    headers = await get_auth_headers(client, "update_test@x.com")
    res = await client.post("/api/persons", json={"full_name": "Сыдыков Омор", "force": True}, headers=headers)
    pid = res.json()["id"]

    upd = await client.put(f"/api/persons/{pid}", json={"full_name": "Сыдыков Омор-Updated"}, headers=headers)
    assert upd.status_code == 200
    assert upd.json()["full_name"] == "Сыдыков Омор-Updated"


@pytest.mark.asyncio
async def test_get_nonexistent_person(client: AsyncClient):
    res = await client.get("/api/persons/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
