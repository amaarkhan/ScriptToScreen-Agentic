from __future__ import annotations

from typing import Any

from .registry import Phase2MCPRegistry
from .tools import TOOL_HANDLERS


class Phase2MCPRuntime:
    def __init__(self, config_path: str) -> None:
        self.registry = Phase2MCPRegistry(config_path)

    def invoke_capability(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self.registry.discover_by_capability(capability)
        if tool is None:
            return {
                "ok": False,
                "error": {
                    "code": "MCP_TOOL_NOT_FOUND",
                    "message": f"No tool discovered for capability '{capability}'.",
                },
            }

        schema = tool.get("schema", {})
        required = schema.get("required", [])
        types = schema.get("types", {})

        for key in required:
            if key not in payload:
                return {
                    "ok": False,
                    "tool": tool["name"],
                    "error": {"code": "MCP_SCHEMA_VALIDATION_FAILED", "message": f"Missing required field: {key}"},
                }

        for key, expected in types.items():
            if key in payload:
                value = payload[key]
                if expected == "string" and not isinstance(value, str):
                    return {
                        "ok": False,
                        "tool": tool["name"],
                        "error": {"code": "MCP_SCHEMA_VALIDATION_FAILED", "message": f"Field '{key}' must be a string."},
                    }
                if expected == "object" and not isinstance(value, dict):
                    return {
                        "ok": False,
                        "tool": tool["name"],
                        "error": {"code": "MCP_SCHEMA_VALIDATION_FAILED", "message": f"Field '{key}' must be an object."},
                    }
                if expected == "array" and not isinstance(value, list):
                    return {
                        "ok": False,
                        "tool": tool["name"],
                        "error": {"code": "MCP_SCHEMA_VALIDATION_FAILED", "message": f"Field '{key}' must be an array."},
                    }
                if expected == "integer" and not isinstance(value, int):
                    return {
                        "ok": False,
                        "tool": tool["name"],
                        "error": {"code": "MCP_SCHEMA_VALIDATION_FAILED", "message": f"Field '{key}' must be an integer."},
                    }

        handler = TOOL_HANDLERS.get(tool["name"])
        if handler is None:
            return {
                "ok": False,
                "tool": tool["name"],
                "error": {"code": "MCP_HANDLER_MISSING", "message": f"No handler registered for '{tool['name']}'."},
            }

        try:
            result = handler(payload)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "tool": tool["name"],
                "error": {
                    "code": "MCP_HANDLER_EXECUTION_FAILED",
                    "message": str(exc),
                },
            }
        return {"ok": True, "tool": tool["name"], "result": result}
