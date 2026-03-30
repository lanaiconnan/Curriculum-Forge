"""共享结果模块"""

import os
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExperimentRecord:
    commit: str
    timestamp: str
    bpb_score: float
    memory_mb: float
    status: str
    description: str
    
    def to_tsv(self) -> str:
        return f"{self.commit}\t{self.timestamp}\t{self.bpb_score:.6f}\t{self.memory_mb:.1f}\t{self.status}\t{self.description}"
    
    @classmethod
    def from_tsv(cls, line: str):
        parts = line.strip().split("\t")
        return cls(parts[0], parts[1], float(parts[2]), float(parts[3]), parts[4], parts[5])


class ResultsLog:
    HEADER = "commit\ttimestamp\tbpb_score\tmemory_mb\tstatus\tdescription"
    
    def __init__(self, path: str = "results.tsv"):
        self.path = path
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(self.HEADER + "\n")
    
    def append(self, record: ExperimentRecord):
        with open(self.path, "a") as f:
            f.write(record.to_tsv() + "\n")
    
    def read_all(self):
        records = []
        with open(self.path) as f:
            for line in f.readlines()[1:]:
                if line.strip():
                    try:
                        records.append(ExperimentRecord.from_tsv(line))
                    except:
                        pass
        return records
    
    def get_stats(self):
        records = self.read_all()
        if not records:
            return {"total": 0, "keep": 0, "keep_rate": 0.0, "best_score": 0.0}
        keeps = sum(1 for r in records if r.status == "keep")
        scores = [r.bpb_score for r in records if r.status == "keep"]
        return {
            "total": len(records),
            "keep": keeps,
            "keep_rate": keeps / len(records),
            "best_score": min(scores) if scores else 0.0,
        }
