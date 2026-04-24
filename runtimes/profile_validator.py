"""
Profile Schema Validator

Validates profile JSON against a defined schema and provides
configuration merging helpers.

Schema version: 1.0
Python: 3.7+
"""

from __future__ import annotations

import copy
import logging
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Schema Definition ────────────────────────────────────────────────────────

REQUIRED_FIELDS = ["name", "version"]

OPTIONAL_FIELDS = {
    "description": str,
    "providers": list,
    "defaults": dict,
    "runtime": dict,
    "metadata": dict,
}

# Known default keys and their types
DEFAULT_KEYS: Dict[str, type] = {
    "topic": str,
    "difficulty": str,  # beginner | intermediate | advanced
    "pass_threshold": (int, float),  # 0.0 - 1.0
    "max_iterations": int,
    "goal": str,
    "disclosure_mode": bool,
    "wait_for_input": bool,
    "interactive": bool,
    "waiting_behavior": str,
}

# Hardcoded service defaults (from pipeline_factory.py)
SERVICE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "environment": {
        "max_tasks_beginner": 2,
        "max_tasks_intermediate": 3,
        "max_tasks_advanced": 5,
    },
    "learner": {
        "max_iterations": 3,
        "llm_backend": "mock",
        "llm_model": "mock",
    },
}


# ── Validation ─────────────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Profile validation failed."""

    pass


def validate_profile(data: Dict[str, Any]) -> List[str]:
    """
    Validate a profile dict against the schema.

    Returns:
        List of error messages (empty if valid).
    """
    errors = []

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: '{field}'")

    # Type checks for optional fields
    for field, expected in OPTIONAL_FIELDS.items():
        if field in data and not isinstance(data[field], expected):
            errors.append(
                f"Field '{field}' must be {expected.__name__}, "
                f"got {type(data[field]).__name__}"
            )

    # Validate defaults keys
    if "defaults" in data:
        for key, value in data["defaults"].items():
            if key in DEFAULT_KEYS:
                expected = DEFAULT_KEYS[key]
                if not isinstance(value, expected):
                    errors.append(
                        f"defaults['{key}'] must be {expected.__name__}, "
                        f"got {type(value).__name__}"
                    )
            # Allow unknown keys but warn
            else:
                logger.debug(f"Unknown defaults key: {key}")

    # Validate providers list
    if "providers" in data:
        valid_providers = [
            "CurriculumProvider",
            "HarnessProvider",
            "MemoryProvider",
            "ReviewProvider",
        ]
        for p in data["providers"]:
            if p not in valid_providers:
                errors.append(f"Unknown provider: '{p}'")

    # Validate difficulty
    if "defaults" in data and "difficulty" in data["defaults"]:
        valid = ("beginner", "intermediate", "advanced")
        if data["defaults"]["difficulty"] not in valid:
            errors.append(
                f"defaults['difficulty'] must be one of {valid}, "
                f"got '{data['defaults']['difficulty']}'"
            )

    # Validate pass_threshold range
    if "defaults" in data and "pass_threshold" in data["defaults"]:
        v = data["defaults"]["pass_threshold"]
        if not (0.0 <= v <= 1.0):
            errors.append(f"defaults['pass_threshold'] must be 0.0-1.0, got {v}")

    return errors


def validate_profile_file(path: Path) -> Tuple[bool, List[str]]:
    """
    Load and validate a profile JSON file.

    Returns:
        (is_valid, error_list)
    """
    if not path.exists():
        return False, [f"File not found: {path}"]

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"JSON parse error: {e}"]

    errors = validate_profile(data)
    return len(errors) == 0, errors


# ── Config Merging ─────────────────────────────────────────────────────────────

def _apply_env_overrides(base: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply environment variable overrides to a config dict.

    Env var format:
        CF_TOPIC=Python Advanced
        CF_MAX_ITERATIONS=20
        CF_PASS_THRESHOLD=0.8
    """
    result = copy.deepcopy(base)
    changed = False

    for key, env_name in [
        ("topic", "CF_TOPIC"),
        ("max_iterations", "CF_MAX_ITERATIONS"),
        ("pass_threshold", "CF_PASS_THRESHOLD"),
        ("difficulty", "CF_DIFFICULTY"),
        ("goal", "CF_GOAL"),
    ]:
        value = os.environ.get(env_name)
        if value is not None:
            # Type conversion based on DEFAULT_KEYS
            if key in DEFAULT_KEYS:
                expected = DEFAULT_KEYS[key]
                if expected == int:
                    value = int(value)
                elif expected == float:
                    value = float(value)
            result[key] = value
            changed = True

    return result


def merge_config(
    profile_data: Dict[str, Any],
    api_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge config from multiple sources, priority: defaults < profile < env < api_overrides.

    Args:
        profile_data: Loaded profile JSON dict.
        api_overrides: Runtime overrides from API (POST /jobs config_overrides).

    Returns:
        Merged effective config dict.
    """
    # Start with service defaults (lowest priority)
    result: Dict[str, Any] = {}

    # Merge profile defaults
    if "defaults" in profile_data:
        result.update(profile_data["defaults"])

    # Merge profile runtime
    if "runtime" in profile_data:
        result.update(profile_data["runtime"])

    # Apply env var overrides
    result = _apply_env_overrides(result)

    # Apply API overrides (highest priority)
    if api_overrides:
        result.update(api_overrides)

    return result


def get_effective_defaults(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return the resolved defaults for a profile, including service-level defaults.

    This shows what values will be used when a job runs with this profile,
    before any API overrides.
    """
    defaults = dict(SERVICE_DEFAULTS.get("learner", {}))

    if "defaults" in profile_data:
        defaults.update(profile_data["defaults"])

    return defaults


def get_service_defaults(service_name: str) -> Dict[str, Any]:
    """Get hardcoded defaults for a service."""
    return dict(SERVICE_DEFAULTS.get(service_name, {}))


# ── Profile Discovery ──────────────────────────────────────────────────────────

def discover_profiles(profiles_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Find all profile JSON files in the profiles directory.

    Args:
        profiles_dir: Path to profiles directory. Defaults to ./profiles relative to this file.

    Returns:
        List of profile info dicts (name, file, description, valid, errors).
    """
    if profiles_dir is None:
        profiles_dir = Path(__file__).resolve().parent.parent / "profiles"

    profiles_dir.mkdir(exist_ok=True)
    results = []

    for p in sorted(profiles_dir.glob("*.json")):
        is_valid, errors = validate_profile_file(p)
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        results.append({
            "name": p.stem,
            "file": p.name,
            "description": data.get("description", ""),
            "valid": is_valid,
            "errors": errors,
        })

    return results
