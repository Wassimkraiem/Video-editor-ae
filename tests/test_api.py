import io

from fastapi.testclient import TestClient

from services.api.main import app, repo


def setup_function():
    repo.users.clear()
    repo.projects.clear()
    repo.assets.clear()
    repo.timelines.clear()


def test_auth_project_timeline_and_streamed_upload():
    with TestClient(app) as client:
        registered = client.post("/api/v1/auth/register", json={"email": "owner@example.com", "password": "correct horse battery staple"})
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        project = client.post("/api/v1/projects", headers=headers, json={"name": "Demo", "workflow": "raw-footage"})
        assert project.status_code == 201
        project_id = project.json()["id"]
        upload = client.post("/api/v1/projects/%s/assets" % project_id, headers=headers, files={"file": ("clip.mp4", io.BytesIO(b"video-bytes"), "video/mp4")})
        assert upload.status_code == 201
        versions = client.get(f"/api/v1/projects/{project_id}/timeline/versions", headers=headers)
        assert versions.status_code == 200
        assert versions.json()[0]["version"] == 1


def test_project_authorization_is_enforced():
    with TestClient(app) as client:
        owner = client.post("/api/v1/auth/register", json={"email": "owner@example.com", "password": "correct horse battery staple"})
        other = client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "correct horse battery staple"})
        project = client.post("/api/v1/projects", headers={"Authorization": f"Bearer {owner.json()['access_token']}"}, json={"name": "Private"})
        response = client.get(f"/api/v1/projects/{project.json()['id']}", headers={"Authorization": f"Bearer {other.json()['access_token']}"})
        assert response.status_code == 404
