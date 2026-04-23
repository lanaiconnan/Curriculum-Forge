# Per-run Workspace Isolation Spec

## Problem
All jobs share:
- Same `workspace="."` for EnvironmentService / LearnerService
- Same `~/.curriculum-forge/checkpoints/` flat directory
- No per-run temp/scratch space

Concurrent runs would:
- Write to same `results.tsv` → data corruption
- Share same task templates / scratch files → cross-contamination
- No way to clean up a single run's artifacts

## Design

### RunWorkspace
A per-run directory that isolates all file I/O for a single job execution.

```
~/.curriculum-forge/
├── checkpoints/           # Global checkpoint index (unchanged)
│   ├── run_20260423_120000.json
│   └── run_20260423_130000.json
└── workspaces/            # NEW: per-run workspace roots
    ├── run_20260423_120000/
    │   ├── results.tsv
    │   ├── scratch/
    │   ├── logs/
    │   └── artifacts/
    └── run_20260423_130000/
        ├── results.tsv
        ├── scratch/
        ├── logs/
        └── artifacts/
```

### RunWorkspace class
```python
class RunWorkspace:
    """Per-run workspace isolation."""
    
    def __init__(self, run_id: str, base_dir: Path = WORKSPACE_BASE):
        self.run_id = run_id
        self.root = base_dir / run_id
        self.scratch_dir = self.root / "scratch"
        self.logs_dir = self.root / "logs"
        self.artifacts_dir = self.root / "artifacts"
        self.results_file = self.root / "results.tsv"
        # Create dirs
        self.root.mkdir(parents=True, exist_ok=True)
        self.scratch_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
    
    def cleanup(self) -> None:
        """Remove entire workspace directory."""
        shutil.rmtree(self.root, ignore_errors=True)
    
    def workspace_path(self) -> str:
        """Return root path as string (for services that take workspace:str)."""
        return str(self.root)
```

### Integration Points

1. **CheckpointRecord** — add `workspace_dir: Optional[str]` field
2. **pipeline_factory.create_pipeline()** — accept `workspace_dir`, create RunWorkspace, pass to services
3. **AdaptiveRuntime** — hold `RunWorkspace`, expose to providers via `runtime.workspace`
4. **Gateway._run_job_background()** — create RunWorkspace before running
5. **Providers** — use `runtime.workspace.workspace_path()` instead of hardcoded `"."`
6. **EnvironmentService/LearnerService** — use the per-run workspace path
7. **Cleanup** — add `DELETE /jobs/{id}/workspace` endpoint + auto-cleanup on job deletion

### Backward Compatibility
- If no workspace_dir provided → use `.` (current behavior)
- RunWorkspace created lazily (only when a job actually runs)
- Existing CheckpointRecord without workspace_dir still valid

## Files to Modify
1. `runtimes/workspace.py` — NEW: RunWorkspace class
2. `runtimes/checkpoint_store.py` — add workspace_dir to CheckpointRecord
3. `runtimes/adaptive_runtime.py` — add workspace property
4. `runtimes/pipeline_factory.py` — integrate RunWorkspace creation
5. `runtimes/gateway.py` — create workspace on job start, add cleanup endpoint
6. `providers/curriculum_provider.py` — use runtime.workspace
7. `providers/harness_provider.py` — use runtime.workspace
8. `providers/memory_provider.py` — use runtime.workspace
9. `providers/review_provider.py` — use runtime.workspace
10. `tests/unit/test_workspace.py` — NEW: workspace isolation tests
