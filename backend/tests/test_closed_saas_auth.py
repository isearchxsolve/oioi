"""High-signal integration coverage for the owner-operated SaaS boundary."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from app.core import database
    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'closed-saas.db'}")
    monkeypatch.setattr(settings, "OWNER_EMAIL", "owner@example.test")
    monkeypatch.setattr(settings, "OWNER_INITIAL_PASSWORD", "Owner-password-2026")
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "DEBUG", False)
    database.engine = None
    database.async_session_maker = None
    database._schema_initialized = False
    with TestClient(app) as test_client:
        yield test_client
    if database.engine is not None:
        asyncio.run(database.engine.dispose())
    database.engine = None
    database.async_session_maker = None
    database._schema_initialized = False


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_owner_controls_accounts_and_public_signup_is_closed(client: TestClient) -> None:
    assert client.post("/api/v1/auth/signup", json={}).status_code == 403
    assert client.get("/api/v1/projects/").status_code == 401

    owner_headers = _login(client, "owner@example.test", "Owner-password-2026")
    created = client.post(
        "/api/v1/auth/users",
        json={"email": "paid.customer@example.test", "password": "Customer-password-2026", "name": "Paid Customer"},
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    customer = created.json()
    assert customer["is_admin"] is False

    customer_headers = _login(client, "paid.customer@example.test", "Customer-password-2026")
    assert client.get("/api/v1/auth/users", headers=customer_headers).status_code == 403
    # The sole administrator cannot be modified through the customer-management API.
    assert client.patch(f"/api/v1/auth/users/{created.json()['id']}", json={"is_active": False}, headers=owner_headers).status_code == 200


def test_profiles_passwords_and_projects_are_tenant_scoped(client: TestClient) -> None:
    owner_headers = _login(client, "owner@example.test", "Owner-password-2026")
    created = client.post(
        "/api/v1/auth/users",
        json={"email": "customer@example.test", "password": "Customer-password-2026"}, headers=owner_headers,
    )
    customer_id = created.json()["id"]
    customer_headers = _login(client, "customer@example.test", "Customer-password-2026")

    owner_project = client.post("/api/v1/projects/", json={"title": "Owner film"}, headers=owner_headers).json()
    customer_project = client.post("/api/v1/projects/", json={"title": "Customer film"}, headers=customer_headers)
    assert customer_project.status_code == 200
    assert client.get(f"/api/v1/projects/{owner_project['id']}", headers=customer_headers).status_code == 404
    assert [item["title"] for item in client.get("/api/v1/projects/", headers=customer_headers).json()] == ["Customer film"]

    profile = client.patch(
        "/api/v1/auth/me", json={"email": "customer.one@example.test", "name": "Customer One"}, headers=customer_headers,
    ).json()
    assert profile["name"] == "Customer One"
    assert profile["email"] == "customer.one@example.test"
    changed = client.post(
        "/api/v1/auth/me/password",
        json={"current_password": "Customer-password-2026", "new_password": "New-customer-password-2026"},
        headers=customer_headers,
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me", headers=customer_headers).status_code == 401
    renewed_customer_headers = _login(client, "customer.one@example.test", "New-customer-password-2026")
    assert client.patch(f"/api/v1/auth/users/{customer_id}", json={"name": "not allowed"}, headers=renewed_customer_headers).status_code == 403
