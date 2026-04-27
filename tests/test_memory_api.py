"""
Tests for Knowledge Layer API endpoints
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path
from fastapi.testclient import TestClient

from runtimes.gateway import create_app
from knowledge.syzygy import SyzygyVault


@pytest.fixture
def client():
    """Create test client"""
    app = create_app()
    client = TestClient(app)
    yield client


@pytest.fixture(autouse=True)
def clean_vault(client):
    """Clean vault before each test"""
    # Get vault path from app
    from runtimes.gateway import PROJECT_ROOT
    vault_path = PROJECT_ROOT / "vault"
    
    # Clean before test
    if vault_path.exists():
        for f in vault_path.glob("*.md"):
            f.unlink()
    
    yield
    
    # Clean after test
    if vault_path.exists():
        for f in vault_path.glob("*.md"):
            f.unlink()


class TestMemoryPages:
    """Test /memory/pages endpoints"""
    
    def test_list_pages_empty(self, client):
        """Test listing pages when vault is empty"""
        resp = client.get("/memory/pages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["pages"] == []
    
    def test_create_page(self, client):
        """Test creating a page"""
        resp = client.post("/memory/pages", json={
            "title": "Test Experience",
            "content": "This is a test experience",
            "tags": ["test", "example"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is True
        assert data["title"] == "Test Experience"
    
    def test_list_pages_with_content(self, client):
        """Test listing pages after creation"""
        # Create a page
        client.post("/memory/pages", json={
            "title": "API Optimization",
            "content": "Used caching to improve performance",
            "tags": ["performance", "cache"],
        })
        
        resp = client.get("/memory/pages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["title"] == "API Optimization"
    
    def test_get_page(self, client):
        """Test getting a specific page"""
        # Create a page
        client.post("/memory/pages", json={
            "title": "Database Optimization",
            "content": "Added indexes to improve query performance",
            "tags": ["database", "performance"],
        })
        
        resp = client.get("/memory/pages/Database Optimization")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Database Optimization"
        assert "indexes" in data["content"]
        assert "database" in data["tags"]
    
    def test_get_page_not_found(self, client):
        """Test getting non-existent page"""
        resp = client.get("/memory/pages/Nonexistent")
        assert resp.status_code == 404
    
    def test_list_pages_filter_by_tag(self, client):
        """Test filtering pages by tag"""
        # Create multiple pages
        client.post("/memory/pages", json={
            "title": "Cache Strategy",
            "content": "Redis caching",
            "tags": ["cache", "redis"],
        })
        client.post("/memory/pages", json={
            "title": "Database Index",
            "content": "Added index",
            "tags": ["database"],
        })
        
        resp = client.get("/memory/pages?tag=cache")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["pages"][0]["title"] == "Cache Strategy"


class TestMemoryRetrieve:
    """Test /memory/retrieve endpoint"""
    
    def test_retrieve_empty(self, client):
        """Test retrieval with empty vault"""
        resp = client.post("/memory/retrieve", json={
            "task_id": "task_001",
            "task_type": "optimization",
            "description": "Improve API response time",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task_001"
        assert len(data["relevant_experiences"]) == 0
        assert data["confidence_score"] == 0.0
    
    def test_retrieve_by_type(self, client):
        """Test retrieval by task type tag"""
        # Create matching experience
        client.post("/memory/pages", json={
            "title": "Previous Optimization",
            "content": "Used caching for optimization",
            "tags": ["optimization", "performance"],
        })
        
        resp = client.post("/memory/retrieve", json={
            "task_id": "task_002",
            "task_type": "optimization",
            "description": "Need to optimize API",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["relevant_experiences"]) >= 1
        assert data["confidence_score"] > 0.0
    
    def test_retrieve_by_keyword(self, client):
        """Test retrieval by keyword in description"""
        # Create experience with keyword
        client.post("/memory/pages", json={
            "title": "Redis Cache",
            "content": "Implemented Redis caching for better performance",
            "tags": ["redis", "cache"],
        })
        
        resp = client.post("/memory/retrieve", json={
            "task_id": "task_003",
            "task_type": "database",
            "description": "Need caching optimization",  # Contains 'caching'
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should find the cache experience by keyword 'caching'
        assert len(data["relevant_experiences"]) >= 1


class TestMemoryStore:
    """Test /memory/store endpoint"""
    
    def test_store_experience(self, client):
        """Test storing an experience"""
        resp = client.post("/memory/store", json={
            "task_id": "task_004",
            "task_type": "optimization",
            "background": "API was slow",
            "approach": "Added caching",
            "result": "10x improvement",
            "lessons": "Caching is effective",
            "tags": ["performance", "cache"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] is True
        assert "task_004" in data["task_id"]
    
    def test_store_and_retrieve(self, client):
        """Test storing and then retrieving"""
        # Store experience
        client.post("/memory/store", json={
            "task_id": "task_005",
            "task_type": "testing",
            "background": "Need tests",
            "approach": "Wrote pytest tests",
            "result": "All passing",
            "tags": ["test"],
        })
        
        # Retrieve by type
        resp = client.post("/memory/retrieve", json={
            "task_id": "task_006",
            "task_type": "testing",
            "description": "Write more tests",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["relevant_experiences"]) >= 1


class TestMemoryStats:
    """Test /memory/stats endpoint"""
    
    def test_stats_empty(self, client):
        """Test stats with empty vault"""
        resp = client.get("/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pages"] == 0
        assert data["tag_distribution"] == {}
    
    def test_stats_with_pages(self, client):
        """Test stats with pages"""
        # Create pages
        client.post("/memory/pages", json={
            "title": "Page 1",
            "content": "Content 1",
            "tags": ["tag1", "tag2"],
        })
        client.post("/memory/pages", json={
            "title": "Page 2",
            "content": "Content 2",
            "tags": ["tag1"],
        })
        
        resp = client.get("/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pages"] == 2
        assert data["tag_distribution"]["tag1"] == 2
        assert data["tag_distribution"]["tag2"] == 1


class TestMemorySearch:
    """Test /memory/search endpoint"""
    
    def test_search_empty(self, client):
        """Test search with empty vault"""
        resp = client.get("/memory/search?q=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert data["total"] == 0
    
    def test_search_with_results(self, client):
        """Test search with results"""
        client.post("/memory/pages", json={
            "title": "Redis Caching",
            "content": "Implemented Redis for caching",
            "tags": ["cache"],
        })
        
        resp = client.get("/memory/search?q=Redis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert "Redis" in data["results"][0]["title"]


class TestMemoryGraph:
    """Test /memory/graph endpoint"""
    
    def test_graph_empty(self, client):
        """Test graph with empty vault"""
        resp = client.get("/memory/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "graph" in data
    
    def test_graph_with_pages(self, client):
        """Test graph with pages"""
        client.post("/memory/pages", json={
            "title": "Linked Page",
            "content": "[[Other Page]] link",
            "tags": ["test"],
        })
        
        resp = client.get("/memory/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "graph" in data
