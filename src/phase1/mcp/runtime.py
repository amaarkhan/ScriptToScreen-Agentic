from __future__ import annotations

from typing import Any

from .registry import MCPRegistry
from .tools import TOOL_HANDLERS


def _type_ok(expected: str, value: Any) -> bool:
    checks = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    validator = checks.get(expected)
    return bool(validator and validator(value))


class MCPRuntime:
    def __init__(self, config_path: str) -> None:
        self.registry = MCPRegistry(config_path)

    def invoke_capability(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self.registry.discover_by_capability(capability)
        if tool is None:
            return {
                "ok": False,
                "error": {
                    "code": "MCP_TOOL_NOT_FOUND",
                    "message": f"No MCP tool discovered for capability '{capability}'.",
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
                    "error": {
                        "code": "MCP_SCHEMA_VALIDATION_FAILED",
                        "message": f"Missing required field: {key}",
                    },
                }

        for key, expected in types.items():
            if key in payload and not _type_ok(expected, payload[key]):
                return {
                    "ok": False,
                    "tool": tool["name"],
                    "error": {
                        "code": "MCP_SCHEMA_VALIDATION_FAILED",
                        "message": f"Field '{key}' expected type '{expected}'.",
                    },
                }

        handler = TOOL_HANDLERS.get(tool["name"])
        if handler is None:
            return {
                "ok": False,
                "tool": tool["name"],
                "error": {
                    "code": "MCP_HANDLER_MISSING",
                    "message": f"No handler registered for tool '{tool['name']}'.",
                },
            }

        result = handler(payload)
        return {"ok": True, "tool": tool["name"], "result": result}
