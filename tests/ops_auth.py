from fastapi.testclient import TestClient


def ops_headers(client: TestClient, *, actor_id: str = "ops_test", actor_role: str = "ops") -> dict[str, str]:
    registered = client.post(
        "/v1/auth/register",
        json={"actor_id": actor_id, "actor_role": actor_role, "password": "secret123", "account_id": actor_id},
    )
    assert registered.status_code == 200
    login = client.post("/v1/auth/login", json={"actor_id": actor_id, "password": "secret123"})
    assert login.status_code == 200
    token = login.json()["token"]["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}
