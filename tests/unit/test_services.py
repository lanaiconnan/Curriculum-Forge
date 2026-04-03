"""Unit tests for Service Architecture

Run: pytest tests/unit/test_services.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.base import (
    ServiceBase,
    ServiceConfig,
    ServiceState,
    ServiceMetrics,
    ServiceError,
)
from services.container import (
    ServiceRegistry,
    ServiceContainer,
    ServiceProvider,
)
from services.models import (
    TrainingEnvironment,
    TaskConfig,
    ExperimentRecord,
    ExperimentStatus,
    LearningStage,
    ProgressMetrics,
    RewardBreakdown,
)
from services.environment import (
    EnvironmentService,
    EnvironmentServiceConfig,
)
from services.learner import (
    LearnerService,
    LearnerServiceConfig,
)
from services.trainer import (
    RLTrainerService,
    RLConfig,
    Experience,
)


class TestServiceBase:
    """Test ServiceBase lifecycle"""
    
    def test_service_config(self):
        """Test ServiceConfig creation"""
        config = ServiceConfig(name="test")
        assert config.name == "test"
        assert config.enabled == True
    
    def test_service_metrics(self):
        """Test ServiceMetrics"""
        metrics = ServiceMetrics()
        assert metrics.uptime == 0.0
        assert metrics.error_rate == 0.0
    
    def test_service_state_enum(self):
        """Test ServiceState enum"""
        assert ServiceState.CREATED.value == "created"
        assert ServiceState.RUNNING.value == "running"


class TestModels:
    """Test data models"""
    
    def test_task_config(self):
        """Test TaskConfig"""
        task = TaskConfig(
            id="t1",
            type="optimize",
            description="Test task",
            target="score > 100",
        )
        assert task.id == "t1"
        assert task.max_duration == 300
    
    def test_training_environment(self):
        """Test TrainingEnvironment"""
        env = TrainingEnvironment(
            id="env1",
            name="Test Env",
            description="Test",
            stage=LearningStage.BEGINNER,
            difficulty=0.3,
        )
        assert env.task_count == 0
        assert env.difficulty_level == "medium"  # 0.3 is at the boundary
    
    def test_experiment_record(self):
        """Test ExperimentRecord"""
        from datetime import datetime
        record = ExperimentRecord(
            commit="exp1",
            timestamp=datetime.now(),
            bpb_score=1.5,
            memory_mb=256,
            status=ExperimentStatus.KEEP,
            description="Test",
        )
        assert record.is_keep == True
    
    def test_progress_metrics(self):
        """Test ProgressMetrics"""
        metrics = ProgressMetrics(
            total_experiments=10,
            keep_count=5,
        )
        assert metrics.keep_rate == 0.0  # Calculated from records
    
    def test_reward_breakdown(self):
        """Test RewardBreakdown"""
        reward = RewardBreakdown(
            rformat=1.0,
            rname=1.0,
            rparam=0.5,
            rvalue=0.5,
        )
        assert reward.rcorrect == 2.0  # 1.0 + 0.5 + 0.5
        assert reward.rfinal == 3.0    # 1.0 + 2.0
        assert reward.is_valid == True


class TestServiceRegistry:
    """Test ServiceRegistry"""
    
    def test_register_service(self):
        """Test service registration"""
        registry = ServiceRegistry()
        config = EnvironmentServiceConfig(name="env")
        service = EnvironmentService(config)
        
        registry.register(service)
        
        assert "env" in registry.list_services()
    
    def test_get_service(self):
        """Test getting service"""
        registry = ServiceRegistry()
        config = EnvironmentServiceConfig(name="env")
        service = EnvironmentService(config)
        
        registry.register(service)
        
        retrieved = registry.get("env")
        assert retrieved is service
    
    def test_get_by_type(self):
        """Test getting service by type"""
        registry = ServiceRegistry()
        config = EnvironmentServiceConfig(name="env")
        service = EnvironmentService(config)
        
        registry.register(service, is_primary=True)
        
        retrieved = registry.get_by_type(EnvironmentService)
        assert retrieved is service


class TestServiceContainer:
    """Test ServiceContainer"""
    
    def test_add_service(self):
        """Test adding service to container"""
        container = ServiceContainer()
        config = EnvironmentServiceConfig(name="env")
        
        container.add(EnvironmentService, config)
        
        # Service not created yet
        assert len(container.registry.list_services()) == 0
    
    def test_initialize_all(self):
        """Test initializing all services"""
        container = ServiceContainer()
        
        container.add(
            EnvironmentService,
            EnvironmentServiceConfig(name="env")
        )
        
        container.initialize_all()
        
        assert len(container.registry.list_services()) == 1


class TestEnvironmentService:
    """Test EnvironmentService"""
    
    def test_determine_stage(self):
        """Test stage determination"""
        config = EnvironmentServiceConfig(name="env")
        service = EnvironmentService(config)
        service.initialize()
        
        # Low keep_rate -> Beginner
        progress = ProgressMetrics(keep_rate=0.2)
        stage = service.determine_stage(progress)
        assert stage == LearningStage.BEGINNER
        
        # Medium keep_rate -> Intermediate
        progress = ProgressMetrics(keep_rate=0.4)
        stage = service.determine_stage(progress)
        assert stage == LearningStage.INTERMEDIATE
        
        # High keep_rate -> Advanced
        progress = ProgressMetrics(keep_rate=0.7)
        stage = service.determine_stage(progress)
        assert stage == LearningStage.ADVANCED
    
    def test_generate_environment(self):
        """Test environment generation"""
        config = EnvironmentServiceConfig(name="env")
        service = EnvironmentService(config)
        service.initialize()
        
        progress = ProgressMetrics(keep_rate=0.2)
        env = service.generate_environment(progress)
        
        assert env.stage == LearningStage.BEGINNER
        assert env.difficulty == 0.3
        assert len(env.tasks) > 0


class TestLearnerService:
    """Test LearnerService"""
    
    def test_compute_reward(self):
        """Test reward computation"""
        config = LearnerServiceConfig(name="learner")
        service = LearnerService(config)
        service.initialize()
        
        # Perfect match
        reward = service.compute_reward(
            tool_name="git",
            expected_tool="git",
            params={"a": 1},
            expected_params={"a": 1},
        )
        assert reward.rformat == 1.0
        assert reward.rname == 1.0
    
    def test_run_experiments(self):
        """Test running experiments"""
        config = LearnerServiceConfig(name="learner", max_iterations=1)
        service = LearnerService(config)
        service.initialize()
        
        env = TrainingEnvironment(
            id="test_env",
            name="Test",
            description="Test",
            stage=LearningStage.BEGINNER,
            difficulty=0.3,
            tasks=[
                TaskConfig(
                    id="t1",
                    type="test",
                    description="Test task",
                    target="pass",
                )
            ],
        )
        
        results = service.run_experiments(env, max_iterations=1)
        assert len(results) > 0


class TestRLTrainerService:
    """Test RLTrainerService"""
    
    def test_compute_grpo_advantage(self):
        """Test GRPO advantage computation"""
        config = RLConfig(name="trainer")
        service = RLTrainerService(config)
        service.initialize()
        
        rewards = [1.0, 2.0, 3.0, 4.0, 5.0]
        advantages = service.compute_grpo_advantage(rewards)
        
        # Advantages should sum to ~0 (normalized)
        assert abs(sum(advantages)) < 0.01
    
    def test_train_step(self):
        """Test training step"""
        config = RLConfig(name="trainer")
        service = RLTrainerService(config)
        service.initialize()
        
        # Add some experiences
        experiences = [
            Experience(
                state={},
                action={},
                reward=1.0,
                next_state={},
                done=False,
            )
            for _ in range(5)
        ]
        
        stats = service.train_step(experiences)
        
        assert stats.experiences == 5
        assert stats.total_reward == 5.0


class TestServiceProvider:
    """Test ServiceProvider"""
    
    def test_configure_and_start(self):
        """Test configuring and starting provider"""
        provider = ServiceProvider()
        
        provider.configure(
            EnvironmentService,
            EnvironmentServiceConfig(name="env")
        )
        
        provider.initialize()
        
        service = provider.get(EnvironmentService)
        assert service is not None
        assert service.state == ServiceState.READY
    
    def test_health_check(self):
        """Test health check"""
        provider = ServiceProvider()
        
        provider.configure(
            EnvironmentService,
            EnvironmentServiceConfig(name="env")
        )
        
        provider.start()
        
        health = provider.health_check()
        assert "services" in health
        assert len(health["services"]) == 1
        
        provider.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
