---
name: stage-tracker
version: 1.0.0
description: Tracks learning stage transitions and emits alerts when stage changes.
hooks:
  - stage:before_transition
  - stage:after_transition
priority: 50
---

# stage-tracker

Tracks learning stage transitions throughout training.

## What it does

- Hooks into `stage:before_transition` to validate transitions
- Hooks into `stage:after_transition` to record and alert on changes
- Maintains a transition history
- Emits warnings on unexpected regressions (e.g. advanced → beginner)

## Transition history format

```python
[
    {"from": "beginner", "to": "intermediate", "at": "2026-04-03T10:00:00", "keep_rate": 0.35},
    {"from": "intermediate", "to": "advanced", "at": "2026-04-03T10:05:00", "keep_rate": 0.65},
]
```
