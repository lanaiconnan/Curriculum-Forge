"""Curriculum-Forge 测试配置

pytest 配置文件，用于：
1. 定义测试路径
2. 配置覆盖率报告
3. 设置测试标记
"""

import pytest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    """配置 pytest 标记"""
    config.addinivalue_line(
        "markers", "unit: 单元测试"
    )
    config.addinivalue_line(
        "markers", "integration: 集成测试"
    )
    config.addinivalue_line(
        "markers", "slow: 慢速测试"
    )
    config.addinivalue_line(
        "markers", "requires_llm: 需要本地 LLM"
    )


def pytest_collection_modifyitems(config, items):
    """自动标记测试"""
    for item in items:
        # 根据文件名自动标记
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        elif "unit" in item.nodeid:
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session", autouse=True)
def reset_role_store_singleton():
    """Reset RoleStore singleton between test sessions to avoid cross-pollution."""
    yield
    try:
        from auth.rbac import reset_role_store
        reset_role_store()
    except Exception:
        pass
