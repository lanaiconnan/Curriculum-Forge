"""Simple Performance Tests

Load tests for core components
"""

import pytest
import time
from knowledge import SyzygyVault


# ===== Knowledge Layer Tests =====

def test_page_creation_performance(tmp_path):
    """Test page creation throughput"""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    vault = SyzygyVault(str(vault_path))
    
    num_pages = 100
    start_time = time.time()
    
    for i in range(num_pages):
        vault.create_page(f"Page-{i}", f"# Page {i}\n\nContent {i}")
    
    elapsed = time.time() - start_time
    throughput = num_pages / elapsed
    
    print(f"\nPage creation: {throughput:.2f} pages/sec")
    assert throughput > 100  # At least 100 pages/sec


def test_search_performance(tmp_path):
    """Test search throughput"""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    vault = SyzygyVault(str(vault_path))
    
    # Pre-populate
    for i in range(200):
        vault.create_page(f"Doc-{i}", f"Document {i} with keyword test")
    
    num_searches = 100
    start_time = time.time()
    
    for _ in range(num_searches):
        results = vault.search_by_keyword("test")
    
    elapsed = time.time() - start_time
    throughput = num_searches / elapsed
    
    print(f"\nSearch: {throughput:.2f} searches/sec")
    assert throughput > 30  # At least 30 searches/sec


def test_backlinks_performance(tmp_path):
    """Test backlink resolution"""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    vault = SyzygyVault(str(vault_path))
    
    # Create linked pages
    for i in range(50):
        content = f"# Page {i}\n\n[[Page-0]]"
        vault.create_page(f"Page-{i}", content)
    
    num_checks = 100
    start_time = time.time()
    
    for _ in range(num_checks):
        backlinks = vault.get_backlinks("Page-0")
    
    elapsed = time.time() - start_time
    throughput = num_checks / elapsed
    
    print(f"\nBacklinks: {throughput:.2f} checks/sec")
    assert throughput > 50  # At least 50 checks/sec


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
