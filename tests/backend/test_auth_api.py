from fastapi.testclient import TestClient

from app.auth.security import verify_password
from app.auth.service import auth_service
from app.db.engine import db_session
from app.main import app


def create_admin(username="king", password="correct-horse-battery"):
    with db_session() as db:
        return auth_service.create_admin(db, username, password)


def test_password_is_argon2_and_session_is_server_side():
    user = create_admin()
    assert user.password_hash.startswith("$argon2")
    assert verify_password("correct-horse-battery", user.password_hash)
    with db_session() as db:
        logged_in, token = auth_service.login(db, "king", "correct-horse-battery", "127.0.0.1")
        assert logged_in.id == user.id
        assert len(token) >= 48
    with db_session() as db:
        validated, session = auth_service.validate_session(db, token)
        assert validated.username == "king"
        assert session.token_hash != token


def test_login_lockout_after_five_failures():
    create_admin()
    for _ in range(5):
        with db_session() as db:
            try:
                auth_service.login(db, "king", "wrong", "loopback")
            except Exception:
                pass
    with db_session() as db:
        try:
            auth_service.login(db, "king", "correct-horse-battery", "loopback")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 429
        else:
            raise AssertionError("第六次登录应被限流")


def test_api_requires_login_and_csrf():
    create_admin()
    with TestClient(app, base_url="http://testserver") as client:
        assert client.get("/health").status_code == 200
        unauthorized = client.get("/api/config")
        assert unauthorized.status_code == 401
        assert set(unauthorized.json()["error"]) == {"code", "message", "request_id"}

        login = client.post("/api/auth/login", json={"username": "king", "password": "correct-horse-battery"})
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=strict" in login.headers["set-cookie"]
        csrf = login.json()["csrf_token"]

        assert client.post("/api/chat/sessions", json={"title": "测试"}).status_code == 403
        created = client.post(
            "/api/chat/sessions",
            json={"title": "测试"},
            headers={"X-CSRF-Token": csrf, "Origin": "http://testserver"},
        )
        assert created.status_code == 201
        session_id = created.json()["id"]
        assert client.get(f"/api/chat/sessions/{session_id}").status_code == 200
        assert client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": csrf, "Origin": "http://testserver"}
        ).status_code == 204
        assert client.get("/api/config").status_code == 401


def test_rejects_untrusted_origin():
    create_admin()
    with TestClient(app, base_url="http://testserver") as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "king", "password": "correct-horse-battery"},
            headers={"Origin": "https://attacker.example"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_rejected"
