"""Tests for api/routes/projects.py — REST endpoint integration tests."""

import pytest


class TestCreateProject:
    def test_success(self, api_client, sample_project_payload):
        response = api_client.post("/api/projects", json=sample_project_payload)
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "healthsync"
        assert data["name"] == "HealthSync"
        assert data["key"] == "HEAL"
        assert data["domain"] == "healthcare"
        assert data["connection_mode"] == "local"
        assert data["data_generated"] is False
        assert "folder_path" in data

    def test_missing_required_field(self, api_client):
        payload = {
            "name": "Test",
            # Missing description_goal, description_users, description_purpose
        }
        response = api_client.post("/api/projects", json=payload)
        assert response.status_code == 422

    def test_missing_name(self, api_client):
        payload = {
            "description_goal": "Goal",
            "description_users": "Users",
            "description_purpose": "Purpose",
        }
        response = api_client.post("/api/projects", json=payload)
        assert response.status_code == 422

    def test_duplicate_returns_409(self, api_client, sample_project_payload):
        api_client.post("/api/projects", json=sample_project_payload)
        response = api_client.post("/api/projects", json=sample_project_payload)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_invalid_connection_mode(self, api_client, sample_project_payload):
        sample_project_payload["connection_mode"] = "invalid"
        response = api_client.post("/api/projects", json=sample_project_payload)
        assert response.status_code == 422

    def test_custom_project_key(self, api_client, sample_project_payload):
        sample_project_payload["project_key"] = "HSYNC"
        response = api_client.post("/api/projects", json=sample_project_payload)
        assert response.status_code == 201
        assert response.json()["key"] == "HSYNC"


class TestListProjects:
    def test_empty(self, api_client):
        response = api_client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert data["projects"] == []
        assert data["count"] == 0

    def test_returns_created_projects(self, api_client, sample_project_payload):
        api_client.post("/api/projects", json=sample_project_payload)
        api_client.post("/api/projects", json={
            "name": "FinTech Pro",
            "description_goal": "Build payment system",
            "description_users": "Merchants",
            "description_purpose": "Process payments",
            "domain": "fintech",
        })
        response = api_client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        names = [p["name"] for p in data["projects"]]
        assert "HealthSync" in names
        assert "FinTech Pro" in names


class TestGetProject:
    def test_exists(self, api_client, sample_project_payload):
        api_client.post("/api/projects", json=sample_project_payload)
        response = api_client.get("/api/projects/healthsync")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "HealthSync"
        assert data["description_goal"] == "Build a healthcare scheduling platform"

    def test_not_found(self, api_client):
        response = api_client.get("/api/projects/nonexistent")
        assert response.status_code == 404


class TestDeleteProject:
    def test_success(self, api_client, sample_project_payload):
        api_client.post("/api/projects", json=sample_project_payload)
        response = api_client.delete("/api/projects/healthsync")
        assert response.status_code == 200
        assert response.json()["id"] == "healthsync"
        # Verify it's gone
        response = api_client.get("/api/projects/healthsync")
        assert response.status_code == 404

    def test_not_found(self, api_client):
        response = api_client.delete("/api/projects/nonexistent")
        assert response.status_code == 404
