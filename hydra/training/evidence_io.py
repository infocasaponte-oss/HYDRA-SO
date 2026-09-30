# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Atomic local evidence writes with bounded retries for transient Windows reader locks."""
import json
import time
from pathlib import Path


def write_json(path:Path,data:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt==7:
                raise
            time.sleep(.025*(attempt+1))
