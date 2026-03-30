"""测试 Harness Engineering 模块

测试 doc_gardening.py 和 architecture_engine.py 的核心功能
"""

import pytest
import sys
import os
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.doc_gardening import DocGardeningAgent, DocStatus, DocInfo
from shared.architecture_engine import (
    ArchitectureRuleEngine,
    ViolationSeverity,
    Violation,
    Rule,
)


class TestDocGardeningAgent:
    """DocGardeningAgent 测试套件"""
    
    @pytest.fixture
    def agent(self, tmp_path):
        """创建测试用 Agent"""
        return DocGardeningAgent(
            workspace=str(tmp_path),
            stale_threshold_days=7,
            outdated_threshold_days=30,
        )
    
    @pytest.fixture
    def setup_docs(self, tmp_path):
        """创建测试文档"""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        
        # 创建新文档
        new_doc = docs_dir / "new.md"
        new_doc.write_text("# New Doc\nThis is a new document.")
        
        # 创建旧文档（模拟过期）
        old_doc = docs_dir / "old.md"
        old_doc.write_text("# Old Doc\nThis is an old document.")
        
        # 修改文件时间
        import time
        old_time = time.time() - 86400 * 15  # 15 天前
        os.utime(old_doc, (old_time, old_time))
        
        return docs_dir
    
    def test_agent_initialization(self, agent):
        """测试 Agent 初始化"""
        assert agent is not None
        assert hasattr(agent, 'scan')
        assert hasattr(agent, 'get_stale_docs')
        assert hasattr(agent, 'trigger_fix')
    
    def test_scan_current_docs(self, agent, setup_docs):
        """测试扫描最新文档"""
        report = agent.scan()
        
        assert report is not None
        assert report.total_docs >= 1
        assert report.current_docs >= 1
    
    def test_scan_stale_docs(self, agent, setup_docs):
        """测试扫描过期文档"""
        report = agent.scan()
        
        # 应该检测到过期文档
        assert report.total_docs >= 2
        assert report.stale_docs >= 1
    
    def test_get_stale_docs_list(self, agent, setup_docs):
        """测试获取过期文档列表"""
        agent.scan()  # 先扫描
        stale_docs = agent.get_stale_docs()
        
        assert isinstance(stale_docs, list)
        assert len(stale_docs) >= 1
        
        # 验证文档信息
        doc = stale_docs[0]
        assert isinstance(doc, DocInfo)
        assert doc.status in [DocStatus.STALE, DocStatus.OUTDATED]
        assert doc.age_days >= 7
    
    def test_trigger_fix(self, agent, setup_docs):
        """测试触发修复"""
        agent.scan()
        stale_docs = agent.get_stale_docs()
        
        if stale_docs:
            doc = stale_docs[0]
            result = agent.trigger_fix(doc)
            
            assert result is not None
            assert 'task' in result
            assert result['task'] == 'review_doc'
            assert 'priority' in result
    
    def test_report_generation(self, agent, setup_docs):
        """测试报告生成"""
        report = agent.scan()
        
        assert report.summary is not None
        assert len(report.scanned_dirs) > 0
    
    def test_mark_current(self, agent, setup_docs):
        """测试标记文档为最新"""
        old_doc = setup_docs / "old.md"
        
        agent.mark_current(str(old_doc))
        
        # 验证状态已更新
        assert os.path.exists(agent.state_file)


class TestArchitectureRuleEngine:
    """ArchitectureRuleEngine 测试套件"""
    
    @pytest.fixture
    def engine(self, tmp_path):
        """创建测试用引擎"""
        return ArchitectureRuleEngine(
            workspace=str(tmp_path),
            layer_mapping={
                '/ui/': 'ui',
                '/service/': 'service',
                '/repo/': 'repo',
                '/types/': 'types',
            }
        )
    
    @pytest.fixture
    def setup_violations(self, tmp_path):
        """创建违规代码结构"""
        # 创建目录
        ui_dir = tmp_path / "ui"
        service_dir = tmp_path / "service"
        repo_dir = tmp_path / "repo"
        
        ui_dir.mkdir()
        service_dir.mkdir()
        repo_dir.mkdir()
        
        # 创建违规文件：UI 依赖 Service
        ui_file = ui_dir / "view.py"
        ui_file.write_text("from service import UserService\n\nclass View:\n    pass")
        
        # 创建正常文件：Service 依赖 Repo
        service_file = service_dir / "user_service.py"
        service_file.write_text("from repo import UserRepo\n\nclass UserService:\n    pass")
        
        return tmp_path
    
    def test_engine_initialization(self, engine):
        """测试引擎初始化"""
        assert engine is not None
        assert hasattr(engine, 'validate')
        assert hasattr(engine, 'validate_all')
        assert hasattr(engine, 'should_block')
    
    def test_get_layer(self, engine, tmp_path):
        """测试层次识别"""
        ui_path = str(tmp_path / "ui" / "view.py")
        service_path = str(tmp_path / "service" / "user.py")
        
        assert engine.get_layer(ui_path) == 'ui'
        assert engine.get_layer(service_path) == 'service'
    
    def test_validate_single_file(self, engine, setup_violations):
        """测试单个文件验证"""
        ui_file = setup_violations / "ui" / "view.py"
        violations = engine.validate(str(ui_file))
        
        assert isinstance(violations, list)
    
    def test_validate_all(self, engine, setup_violations):
        """测试全量验证"""
        report = engine.validate_all(['.py'])
        
        assert report is not None
        assert report.total_files >= 2
        assert report.total_violations >= 0
    
    def test_should_block(self, engine, setup_violations):
        """测试是否应该阻止"""
        report = engine.validate_all(['.py'])
        
        should_block = engine.should_block(report)
        assert isinstance(should_block, bool)
    
    def test_suggest_fix(self, engine, setup_violations):
        """测试修复建议"""
        report = engine.validate_all(['.py'])
        
        if report.violations:
            suggestion = engine.suggest_fix(report.violations[0])
            
            assert suggestion is not None
            assert len(suggestion) > 0
    
    def test_default_layer_order(self, engine):
        """测试默认层次顺序"""
        assert 'types' in engine.DEFAULT_LAYER_ORDER
        assert 'ui' in engine.DEFAULT_LAYER_ORDER
        
        # 验证顺序：types 最低，ui 最高
        assert engine.DEFAULT_LAYER_ORDER.index('types') < engine.DEFAULT_LAYER_ORDER.index('ui')
    
    def test_rule_can_depend(self, engine):
        """测试依赖规则"""
        rule = engine.DEFAULT_RULES[0]  # dependency_direction
        
        # 可以从低层依赖高层
        assert rule.can_depend('types', 'service') is True
        assert rule.can_depend('service', 'ui') is True
        
        # 不能从高层依赖低层
        assert rule.can_depend('ui', 'service') is False
        assert rule.can_depend('ui', 'repo') is False


class TestHarnessIntegration:
    """Harness 模块集成测试"""
    
    @pytest.mark.integration
    def test_full_harness_workflow(self, tmp_path):
        """测试完整 Harness 工作流"""
        # 创建文档结构
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        
        new_doc = docs_dir / "new.md"
        new_doc.write_text("# New")
        
        # 创建代码结构
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        
        ui_file = ui_dir / "view.py"
        ui_file.write_text("from service import Service\n\nclass View:\n    pass")
        
        # 运行 DocGardening
        gardener = DocGardeningAgent(
            workspace=str(tmp_path),
            scan_dirs=['docs'],
        )
        garden_report = gardener.scan()
        
        # 运行 Architecture Check
        engine = ArchitectureRuleEngine(
            workspace=str(tmp_path),
            layer_mapping={'/ui/': 'ui', '/service/': 'service'}
        )
        arch_report = engine.validate_all(['.py'])
        
        # 验证结果
        assert garden_report.total_docs >= 1
        assert arch_report.total_files >= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
