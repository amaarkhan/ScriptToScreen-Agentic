from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.as_posix() not in sys.path:
    sys.path.insert(0, SRC.as_posix())

from phase2.workflow import run_phase2_pipeline


if __name__ == "__main__":
    manifest = ROOT / "output" / "acceptance" / "auto_v4" / "scene_manifest.json"
    result = run_phase2_pipeline(
        manifest.as_posix(),
        "phase2-demo",
        (ROOT / "output" / "phase2_demo").as_posix(),
        str(ROOT / "config" / "phase2_mcp_tools.json"),
    )
    print(json.dumps(result["task_graph"], indent=2))
    print(f"status={result['status']}")
    print(f"checkpoint={result.get('checkpoint_path', 'NA')}")
