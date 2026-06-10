"""
P12 · SRE Ops MCP Server — HuggingFace Space Demo
Interactive demo of the MCP server — call tools directly and see results.
Uses HF Inference API (free tier) for LLM summarization.
gradio==5.29.0 + audioop-lts for Python 3.13 compatibility.
"""

import json
import os
import sys

import gradio as gr
from transformers import pipeline

sys.path.insert(0, os.path.dirname(__file__))
from src.tools import (
    TOOLS, get_audit_log,
    get_slo_status, get_runbook, query_alerts,
    create_incident, get_incident_timeline, summarize_incident,
)

# ── Load model for incident summarization ─────────────────────────────────────
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
print(f"Loading {MODEL}...")
pipe = pipeline(
    "text-generation",
    model=MODEL,
    max_new_tokens=200,
    temperature=0.3,
    do_sample=True,
    device_map="cpu",
)
print("Model loaded.")

SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟠", "info": "🔵",
                  "OK": "✅", "ELEVATED": "🟡", "WARNING": "🟠", "CRITICAL": "🔴"}

# ── Preset demo queries ────────────────────────────────────────────────────────
DEMO_SCENARIOS = {
    "🚨 What's burning right now?": "what_burning",
    "📋 Get runbook for HighErrorRate": "get_runbook",
    "🔍 Check auth-service SLO": "check_slo",
    "📝 Create + summarize incident": "create_and_summarize",
    "📜 View audit log": "audit_log",
}


def run_scenario(scenario_key: str) -> tuple:
    """Run a preset demo scenario and return formatted results."""

    if scenario_key == "what_burning":
        alerts = query_alerts(severity="all")
        slo_results = {}
        for svc in ["auth-service", "api-gateway"]:
            slo_results[svc] = get_slo_status(service_name=svc)

        result_md = "## 🚨 What's Burning Right Now?\n\n"
        result_md += f"### Firing Alerts ({alerts['total_firing']} active)\n\n"
        for a in alerts["alerts"]:
            emoji = SEVERITY_EMOJI.get(a["severity"], "❓")
            result_md += f"**{emoji} {a['id']}** — `{a['service']}`\n"
            result_md += f"{a['summary']} _(firing {a['duration_min']}min)_\n\n"

        result_md += "### SLO Status\n\n"
        result_md += "| Service | Burn Rate | Status | Action |\n"
        result_md += "|---------|-----------|--------|--------|\n"
        for svc, s in slo_results.items():
            emoji = SEVERITY_EMOJI.get(s.get("status", ""), "❓")
            result_md += (
                f"| `{svc}` | {s.get('burn_rate', 0)}x "
                f"| {emoji} {s.get('status', '?')} "
                f"| {s.get('action', '?')} |\n"
            )

        tools_called = ["query_alerts", "get_slo_status (×2)"]

    elif scenario_key == "get_runbook":
        rb = get_runbook(alert_name="HighErrorRate")
        result_md = f"## 📋 Runbook: {rb.get('alert', 'HighErrorRate')}\n\n"
        result_md += "### Immediate Steps\n\n"
        for i, step in enumerate(rb.get("immediate_steps", []), 1):
            result_md += f"{i}. {step}\n"
        result_md += f"\n**Escalation:** {rb.get('escalation', 'N/A')}"
        tools_called = ["get_runbook"]

    elif scenario_key == "check_slo":
        s = get_slo_status(service_name="auth-service")
        emoji = SEVERITY_EMOJI.get(s.get("status", ""), "❓")
        result_md = f"## 🔍 SLO Status — `auth-service`\n\n"
        result_md += f"**Status:** {emoji} {s.get('status')}\n\n"
        result_md += f"| Metric | Value |\n|--------|-------|\n"
        result_md += f"| SLO Target | {s.get('slo_target_pct')}% |\n"
        result_md += f"| Error Rate | {s.get('error_rate_pct')}% |\n"
        result_md += f"| Burn Rate | {s.get('burn_rate')}x |\n"
        result_md += f"| Budget Remaining | {s.get('budget_remaining_pct')}% |\n"
        result_md += f"\n**Action:** {s.get('action')}"
        tools_called = ["get_slo_status"]

    elif scenario_key == "create_and_summarize":
        inc = create_incident(
            title="auth-service HighErrorRate — burn rate 4.6x",
            severity="critical",
            service="auth-service",
            description="Error rate spiked after deploy v2.3.1",
        )
        inc_id = inc["incident_id"]
        summary = summarize_incident(incident_id=inc_id, pipe=pipe)
        timeline = get_incident_timeline(incident_id="INC-DEMO01")

        result_md = f"## 📝 Incident Created + Summarized\n\n"
        result_md += f"**Incident ID:** `{inc_id}` — {inc['message']}\n\n"
        result_md += f"### LLM Summary\n\n{summary.get('summary', '')}\n\n"
        result_md += f"### Demo Timeline (INC-DEMO01)\n\n"
        for e in timeline.get("timeline", [])[:5]:
            result_md += f"- `{e['timestamp'][11:19]}` {e['event']}\n"
        tools_called = ["create_incident", "summarize_incident", "get_incident_timeline"]

    elif scenario_key == "audit_log":
        log = get_audit_log(10)
        result_md = f"## 📜 Audit Log (last {len(log)} entries)\n\n"
        if not log:
            result_md += "_No tool calls yet — run a scenario first._"
        else:
            result_md += "| Time | Tool | Latency | Success |\n"
            result_md += "|------|------|---------|--------|\n"
            for entry in reversed(log):
                ok = "✅" if entry["success"] else "❌"
                result_md += (
                    f"| `{entry['timestamp'][11:19]}` "
                    f"| `{entry['tool']}` "
                    f"| {entry['latency_ms']}ms "
                    f"| {ok} |\n"
                )
        tools_called = ["get_audit_log"]

    else:
        result_md = "Select a scenario above."
        tools_called = []

    tools_md = "**Tools called:** " + " → ".join(f"`{t}`" for t in tools_called)
    return result_md, tools_md


def manual_tool_call(tool_name: str, args_json: str) -> str:
    """Call any tool manually with custom args."""
    if tool_name not in TOOLS:
        return f"❌ Tool '{tool_name}' not found. Available: {list(TOOLS.keys())}"
    try:
        args = json.loads(args_json) if args_json.strip() else {}
        fn = TOOLS[tool_name]["fn"]
        result = fn(**args)
        return f"```json\n{json.dumps(result, indent=2)}\n```"
    except json.JSONDecodeError:
        return "❌ Invalid JSON in args field"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ── Gradio UI ──────────────────────────────────────────────────────────────────
with gr.Blocks(title="P12 · SRE Ops MCP Server", theme=gr.themes.Soft()) as demo:

    gr.Markdown("""
    # ⬡ P12 · SRE Ops MCP Server
    **Staff SRE + AI Engineer Portfolio — Capstone Project**

    A custom **MCP (Model Context Protocol) server** that exposes SRE tools
    as LLM-callable actions. The stdio transport works with **Claude Desktop**
    for real on-call assistance.

    This demo shows the HTTP transport version — call tools interactively.
    """)

    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("## 🎬 Demo Scenarios")
            gr.Markdown("Click a scenario to see multiple MCP tools working together:")

            for label, key in DEMO_SCENARIOS.items():
                btn = gr.Button(label, size="lg")
                result_out = gr.Markdown()
                tools_out = gr.Markdown()
                btn.click(
                    fn=lambda k=key: run_scenario(k),
                    outputs=[result_out, tools_out],
                )

        with gr.Column(scale=2):
            gr.Markdown("## 🔧 Manual Tool Call")
            gr.Markdown("Call any tool directly with custom arguments:")

            tool_select = gr.Dropdown(
                choices=list(TOOLS.keys()),
                label="Select tool",
                value="get_slo_status",
            )
            args_input = gr.Textbox(
                label="Arguments (JSON)",
                value='{"service_name": "auth-service"}',
                lines=3,
            )
            call_btn = gr.Button("⚡ Call Tool", variant="primary")
            manual_result = gr.Markdown()

            call_btn.click(
                fn=manual_tool_call,
                inputs=[tool_select, args_input],
                outputs=[manual_result],
            )

            # Update args example when tool changes
            TOOL_EXAMPLES = {
                "get_slo_status": '{"service_name": "auth-service"}',
                "get_runbook": '{"alert_name": "HighErrorRate"}',
                "query_alerts": '{"severity": "critical"}',
                "create_incident": '{"title": "auth-service down", "severity": "critical", "service": "auth-service"}',
                "get_incident_timeline": '{"incident_id": "INC-DEMO01"}',
                "summarize_incident": '{"incident_id": "INC-DEMO01"}',
            }
            tool_select.change(
                fn=lambda t: TOOL_EXAMPLES.get(t, "{}"),
                inputs=[tool_select],
                outputs=[args_input],
            )

    with gr.Accordion("📖 MCP Protocol + Claude Desktop Setup", open=False):
        gr.Markdown("""
        ## What is MCP?

        MCP (Model Context Protocol) is Anthropic's open standard for connecting
        LLMs to external tools and data sources. It defines how a host (Claude)
        communicates with a server (this code) via JSON-RPC.

        ## How this server works

        ```
        Claude Desktop / MCP Client
              ↓ JSON-RPC over stdio
        SRE Ops MCP Server (this code)
              ↓ calls
        SRE Tools (SLO, runbooks, alerts, incidents)
              ↓ returns
        Structured JSON → Claude synthesizes response
        ```

        ## Use with Claude Desktop

        Add to `~/.claude/claude_desktop_config.json`:
        ```json
        {
          "mcpServers": {
            "sre-ops": {
              "command": "python",
              "args": ["-m", "src.mcp_server"],
              "cwd": "/path/to/p12-sre-mcp"
            }
          }
        }
        ```

        Then ask Claude: _"What's burning right now?"_ and it will call
        `query_alerts` + `get_slo_status` automatically.

        ## SRE additions
        - Every tool call audit logged (postmortem-ready)
        - Tool latency tracked (p95 SLO: <500ms)
        - Graceful fallback when tools fail
        - Rate limiting per client (10 req/min)
        - Auth via API key (set `MCP_API_KEY` env var)
        """)

    gr.Markdown("""
    ---
    [GitHub](https://github.com/amarshiv86/p12-sre-mcp) ·
    [Staff SRE Portfolio](https://github.com/amarshiv86)
    """)

demo.launch()
