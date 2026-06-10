# P14 · SRE Ops MCP Server

Custom **MCP (Model Context Protocol) server** exposing SRE tools as LLM-callable actions.
Capstone project of the [Staff SRE · AI Engineer Portfolio](https://github.com/amarshiv86).

## Where things live

| What | Where |
|------|-------|
| MCP server code | This repo (`src/`) |
| Interactive demo | [HF Space](https://huggingface.co/spaces/amarshiv86/p14-sre-mcp) |
| Tool examples + audit log | [HF Dataset](https://huggingface.co/datasets/amarshiv86/p14-sre-mcp-dataset) |

## Tools exposed

| Tool | Description |
|------|-------------|
| `get_slo_status` | SLO burn rate + error budget per service |
| `get_runbook` | Fetch runbook steps for an alert |
| `query_alerts` | Recent firing alerts by severity |
| `create_incident` | Create incident record |
| `get_incident_timeline` | Timeline of events for an incident |
| `summarize_incident` | LLM-generated incident summary |

## Use with Claude Desktop

```json
{
  "mcpServers": {
    "sre-ops": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/p14-sre-mcp"
    }
  }
}
```

Then ask Claude: _"What's burning right now?"_ — it calls `query_alerts` +
`get_slo_status` automatically and synthesizes a response.

## SRE additions
- Every tool call **audit logged** (timestamp, latency, success — postmortem-ready)
- Tool latency tracked — SLO: p95 < 500ms
- Graceful fallback when tools fail
- JSON-RPC 2.0 protocol compliance
- Both stdio (Claude Desktop) and HTTP (HF Space demo) transports

## Run locally

```bash
git clone https://github.com/amarshiv86/p14-sre-mcp
cd p14-sre-mcp
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start MCP server (stdio transport)
python -m src.mcp_server

# Test with manual JSON-RPC call
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python -m src.mcp_server
```

## Project structure

```
p14-sre-mcp/
├── src/
│   ├── tools.py        # 6 SRE tools + audit logging + timed_tool decorator
│   └── mcp_server.py   # JSON-RPC 2.0 stdio transport
├── tests/
│   └── test_mcp.py     # 20 tests (tools + MCP protocol)
├── hf_space/
│   ├── app.py          # Gradio demo — scenario runner + manual tool call
│   ├── README.md       # sdk_version: 5.29.0
│   └── requirements.txt
├── data/
│   ├── raw/tool_call_examples.jsonl
│   └── processed/sample_audit_log.json
├── .github/workflows/
│   ├── ci.yml
│   ├── deploy-hf-space.yml
│   └── deploy-hf-dataset.yml
└── requirements.txt
```

## Stack

`MCP Protocol` · `JSON-RPC 2.0` · `Qwen2.5-0.5B` · `Gradio 5` · `Audit logging` · `GitHub Actions`
