"""
Curriculum-Forge Role Layer

角色运行时定义（MoonClaw Role Substrate 概念）。
定义 teacher / learner / reviewer 三种角色的运行时契约。
"""

from roles.role_runtime import RolePhase, RoleRuntime, TeacherRole, LearnerRole, ReviewerRole

__all__ = [
    "RolePhase",
    "RoleRuntime",
    "TeacherRole",
    "LearnerRole",
    "ReviewerRole",
]
