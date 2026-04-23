---
name: reward-logger
version: 1.0.0
description: Logs reward breakdown after each experiment. Writes to rewards.log in workspace.
hooks:
  - reward:after_calc
  - exp:after_run
priority: 100
---

# reward-logger

Logs fine-grained reward breakdown after each experiment run.

## What it does

- Hooks into `reward:after_calc` to log each reward component
- Hooks into `exp:after_run` to log experiment summary
- Writes to `rewards.log` in the workspace directory

## Output format

```
[2026-04-03 10:00:00] exp_001 | rformat=1.0 rname=1.0 rparam=0.5 rvalue=0.5 | rfinal=3.0
```
