from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_announcements_home_redirects_unauthenticated():
    # If a user isn't logged in, they should be redirected to the login page
    response = client.get("/announcements", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_new_announcement_redirects_unauthenticated():
    response = client.get("/announcements/new", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"