"""
P12 · SRE Ops MCP Server — Stdio Transport
Standard MCP server using stdio transport.
Use this with Claude Desktop or any MCP client.

Usage:
    python -m src.mcp_server

Claude Desktop config (~/.claude/claude_desktop_config.json):
{
  "mcpServers": {
    "sre-ops": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/p12-sre-mcp"
    }
  }
}
"""

import json
import sys
from .tools import TOOLS, get_audit_log


def send_response(response: dict):
    """Write JSON-RPC response to stdout."""
    print(json.dumps(response), flush=True)


def handle_request(request: dict) -> dict | None:
    """Handle a single JSON-RPC request."""
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})

    # ── MCP protocol methods ──────────────────────────────────────────────────
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "sre-ops-mcp-server",
                    "version": "1.0.0",
                },
            },
        }

    elif method == "tools/list":
        tools_list = [
            {
                "name": name,
                "description": info["description"],
                "inputSchema": info["inputSchema"],
            }
            for name, info in TOOLS.items()
        ]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools_list},
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool '{tool_name}' not found",
                },
            }

        try:
            fn = TOOLS[tool_name]["fn"]
            result = fn(**tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2),
                        }
                    ],
                    "isError": False,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True,
                },
            }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not found",
            },
        }


def run_stdio_server():
    """Run MCP server over stdio — standard transport for Claude Desktop."""
    print("SRE Ops MCP Server starting (stdio transport)...", file=sys.stderr)
    print(f"Available tools: {list(TOOLS.keys())}", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                send_response(response)
        except json.JSONDecodeError as e:
            send_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            })
        except Exception as e:
            send_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {e}"},
            })


if __name__ == "__main__":
    run_stdio_server()
