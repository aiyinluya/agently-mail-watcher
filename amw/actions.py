from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_job_queue(dir_path: Path, job: dict[str, Any]) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{job['messageId']}.json"
    file_path.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return file_path
