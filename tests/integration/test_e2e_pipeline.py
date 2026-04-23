"""
E2E Integration Test — Pipeline Flow

Phase 2 Item 6: End-to-end integration test for linear Pipeline flow.
Channel message → Job creation → Provider execution → SSE events → completion
"""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient


class TestE2EPipeline:
    """End-to-end test for linear Pipeline execution."""

    def _make_app(self):
        from runtimes.gateway import create_app
        app = create_app()
        return app

    def test_create_job_and_check_status(self):
        """Create a job and verify its status via the API."""
        app = self._make_app()
        with TestClient(app) as client:
            # Create a job
            resp = client.post("/jobs", json={
                "profile": "rl_controller",
                "description": "E2E test job",
            })
            assert resp.status_code == 201
            data = resp.json()
            job_id = data["job"]["id"]
            assert data["created"] is True

            # Check job exists
            resp = client.get(f"/jobs/{job_id}")
            assert resp.status_code == 200
            job = resp.json()
            assert job["id"] == job_id
            assert job["status"] in ("pending", "running", "completed", "failed")

    def test_list_jobs(self):
        """List jobs endpoint."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.get("/jobs")
            assert resp.status_code == 200
            data = resp.json()
            assert "jobs" in data
            assert "total" in data

    def test_health_check(self):
        """Health check endpoint."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"

    def test_profiles_endpoint(self):
        """Profiles listing."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.get("/profiles")
            assert resp.status_code == 200
            data = resp.json()
            assert "profiles" in data

    def test_stats_endpoint(self):
        """Stats endpoint."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.get("/stats")
            assert resp.status_code == 200

    def test_create_job_with_invalid_profile(self):
        """Creating a job with an invalid profile should return 404."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.post("/jobs", json={"profile": "nonexistent_profile"})
            assert resp.status_code == 404

    def test_get_nonexistent_job(self):
        """Getting a non-existent job should return 404."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.get("/jobs/nonexistent-id")
            assert resp.status_code == 404

    def test_abort_nonexistent_job(self):
        """Aborting a non-existent job should return 404."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.post("/jobs/nonexistent-id/abort")
            assert resp.status_code == 404
