"""Smoke tests for host web UI serving."""

from fastapi.testclient import TestClient

from boardgame_platform.host import create_app, web_dir


def test_web_dir_exists() -> None:
    d = web_dir()
    assert d.is_dir()
    assert (d / "index.html").is_file()
    assert (d / "app.js").is_file()
    assert (d / "styles.css").is_file()


def test_create_app_serves_index() -> None:
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "桌游联机平台" in body
    assert "/static/app.js" in body


def test_static_and_api_games() -> None:
    client = TestClient(create_app())
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert "0b1e3a" in css.text or "--bg" in css.text

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "create_room" in js.text

    games = client.get("/api/games")
    assert games.status_code == 200
    data = games.json()
    assert "games" in data
    ids = [g["game_id"] for g in data["games"]]
    assert "tictactoe" in ids


def test_health_still_ok() -> None:
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
