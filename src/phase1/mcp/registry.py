from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MCPRegistry:
    def __init__(self, config_path: str) -> None:
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"MCP config not found: {self.config_path}")
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        self._tools: list[dict[str, Any]] = payload.get("tools", [])

    def discover_by_capability(self, capability: str) -> dict[str, Any] | None:
        for tool in self._tools:
            if tool.get("capability") == capability:
                return tool
        return None
