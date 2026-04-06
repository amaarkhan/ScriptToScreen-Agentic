from __future__ import annotations

import importlib
import os
import re
from typing import Any

from .registry import MCPRegistry


def _type_ok(expected: str, value: Any) -> bool:
    checks = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    validator = checks.get(expected)
    return bool(validator and validator(value))


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _resolve_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return os.environ.get(key, "")

        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def _resolve_handler(handler_path: str):
    module_name, _, function_name = handler_path.partition(":")
    if not module_name or not function_name:
        raise ValueError("Handler path must be 'module.path:function_name'.")
    module = importlib.import_module(module_name)
    handler = getattr(module, function_name, None)
    if handler is None or not callable(handler):
        raise AttributeError(f"Handler '{handler_path}' is not callable.")
    return handler


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
        defaults = _resolve_env_vars(tool.get("defaults", {}))
        merged_payload = {**defaults, **payload}
        required = schema.get("required", [])
        types = schema.get("types", {})

        for key in required:
            if key not in merged_payload:
                return {
                    "ok": False,
                    "tool": tool["name"],
                    "error": {
                        "code": "MCP_SCHEMA_VALIDATION_FAILED",
                        "message": f"Missing required field: {key}",
                    },
                }

        for key, expected in types.items():
            if key in merged_payload and not _type_ok(expected, merged_payload[key]):
                return {
                    "ok": False,
                    "tool": tool["name"],
                    "error": {
                        "code": "MCP_SCHEMA_VALIDATION_FAILED",
                        "message": f"Field '{key}' expected type '{expected}'.",
                    },
                }

        handler_path = tool.get("handler")
        if not isinstance(handler_path, str) or not handler_path.strip():
            return {
                "ok": False,
                "tool": tool["name"],
                "error": {
                    "code": "MCP_HANDLER_MISSING",
                    "message": f"No handler configured for tool '{tool['name']}'.",
                },
            }

        try:
            handler = _resolve_handler(handler_path)
            result = handler(merged_payload)
        except Exception as exc:
            return {
                "ok": False,
                "tool": tool["name"],
                "error": {
                    "code": "MCP_HANDLER_EXECUTION_FAILED",
                    "message": f"Failed to execute handler for tool '{tool['name']}'.",
                    "details": str(exc),
                },
            }
        return {"ok": True, "tool": tool["name"], "result": result}
