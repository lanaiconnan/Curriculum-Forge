---
name: experiment-filter
version: 1.0.0
description: Filters out low-quality experiments before they enter the RL training buffer.
hooks:
  - exp:before_run
  - result:before_save
priority: 10
---

# experiment-filter

Filters low-quality experiments before they pollute the RL training buffer.

## What it does

- Hooks into `exp:before_run` to skip experiments with invalid configs
- Hooks into `result:before_save` to filter results below quality threshold
- Configurable min_reward threshold (default: -2.0)
- Tracks filter statistics

## Config

Set via context data:
- `min_reward`: Minimum reward to keep (default -2.0)
- `max_duration`: Maximum experiment duration in seconds (default 60.0)
