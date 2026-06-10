"""
P12 · SRE Ops MCP Server — Tool Definitions
All tools exposed via MCP protocol.
Mix of P08 reused tools + new incident management tools.
Every tool call is audit logged.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Audit log ─────────────────────────────────────────────────────────────────
AUDIT_LOG: list[dict] = []


def audit(tool: str, args: dict, result: Any, latency_ms: int):
    """Log every tool invocation — critical for postmortems."""
    AUDIT_LOG.append({
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": args,
        "success": "error" not in str(result).lower(),
        "latency_ms": latency_ms,
    })
    if len(AUDIT_LOG) > 200:
        AUDIT_LOG.pop(0)


def timed_tool(fn):
    """Decorator that times tool execution and logs to audit trail."""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        latency = int((time.time() - start) * 1000)
        audit(fn.__name__, kwargs, result, latency)
        return result
    wrapper.__name__ = fn.__name__
    return wrapper


# ── Mock data (reuses P08 pattern) ────────────────────────────────────────────
MOCK_SLO_DATA = {
    "api-gateway":          {"slo": 99.9,  "error_rate": 0.08, "burn_rate": 0.85},
    "payment-service":      {"slo": 99.95, "error_rate": 0.02, "burn_rate": 0.44},
    "auth-service":         {"slo": 99.9,  "error_rate": 0.45, "burn_rate": 4.61},
    "notification-service": {"slo": 99.5,  "error_rate": 0.03, "burn_rate": 0.05},
}

MOCK_ALERTS = [
    {"id": "PD-001", "service": "auth-service", "alert": "HighErrorRate",
     "severity": "critical", "duration_min": 47, "status": "firing",
     "summary": "auth-service error rate 0.45% exceeds SLO threshold of 0.1%"},
    {"id": "PD-002", "service": "api-gateway", "alert": "SlowResponseTime",
     "severity": "warning", "duration_min": 14, "status": "firing",
     "summary": "api-gateway p99 latency 850ms exceeds 500ms threshold"},
    {"id": "PD-003", "service": "payment-service", "alert": "CertificateExpiringSoon",
     "severity": "warning", "duration_min": 1032, "status": "firing",
     "summary": "TLS certificate expires in 7 days"},
]

MOCK_RUNBOOKS = {
    "higherrorrate": {
        "alert": "HighErrorRate",
        "immediate_steps": [
            "Check recent deployments: kubectl rollout history deployment/<name>",
            "Check pod logs: kubectl logs -l app=<service> --tail=100",
            "If deployment-related: kubectl rollout undo deployment/<name>",
            "Page secondary on-call if not resolved in 15 minutes",
        ],
        "escalation": "Page on-call lead if burn rate > 14.4x or not resolved in 15min",
    },
    "slowresponsetime": {
        "alert": "SlowResponseTime",
        "immediate_steps": [
            "Check which endpoints are slow: review latency breakdown in Grafana",
            "Check database query latency",
            "Check CPU and memory: kubectl top pods",
            "Check for traffic spike",
        ],
        "escalation": "Escalate if p99 > 2x threshold",
    },
}

# In-memory incident store
INCIDENTS: dict[str, dict] = {}


# ── Tool 1: Get SLO Status ────────────────────────────────────────────────────
@timed_tool
def get_slo_status(service_name: str) -> dict:
    """Get SLO burn rate and error budget status for a service."""
    service_name = service_name.lower().strip()
    if service_name not in MOCK_SLO_DATA:
        return {
            "error": f"Service '{service_name}' not found",
            "available_services": list(MOCK_SLO_DATA.keys()),
        }
    d = MOCK_SLO_DATA[service_name]
    burn = d["burn_rate"]
    status = (
        "CRITICAL" if burn > 14.4 else
        "WARNING" if burn > 6 else
        "ELEVATED" if burn > 1 else
        "OK"
    )
    return {
        "service": service_name,
        "slo_target_pct": d["slo"],
        "error_rate_pct": d["error_rate"],
        "burn_rate": burn,
        "status": status,
        "budget_remaining_pct": round(max(0, 100 - burn * 2), 1),
        "action": (
            "Page on-call immediately" if status == "CRITICAL" else
            "Investigate soon" if status == "WARNING" else
            "Monitor" if status == "ELEVATED" else
            "No action needed"
        ),
    }


# ── Tool 2: Get Runbook ───────────────────────────────────────────────────────
@timed_tool
def get_runbook(alert_name: str) -> dict:
    """Fetch runbook steps for an alert."""
    key = alert_name.lower().replace(" ", "").replace("-", "").replace("_", "")
    for rb_key, rb in MOCK_RUNBOOKS.items():
        if rb_key in key or key in rb_key:
            return rb
    return {
        "error": f"No runbook found for '{alert_name}'",
        "available": list(MOCK_RUNBOOKS.keys()),
    }


# ── Tool 3: Query Alerts ──────────────────────────────────────────────────────
@timed_tool
def query_alerts(severity: str = "all") -> dict:
    """Query recent firing alerts, optionally filtered by severity."""
    severity = severity.lower().strip()
    alerts = MOCK_ALERTS if severity == "all" else [
        a for a in MOCK_ALERTS if a["severity"] == severity
    ]
    return {
        "total_firing": len(alerts),
        "filter": severity,
        "alerts": alerts,
    }


# ── Tool 4: Create Incident ───────────────────────────────────────────────────
@timed_tool
def create_incident(
    title: str,
    severity: str,
    service: str,
    description: str = "",
) -> dict:
    """Create a new incident record."""
    incident_id = f"INC-{str(uuid.uuid4())[:6].upper()}"
    incident = {
        "id": incident_id,
        "title": title,
        "severity": severity,
        "service": service,
        "description": description,
        "status": "investigating",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "timeline": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "Incident created",
                "author": "mcp-server",
            }
        ],
    }
    INCIDENTS[incident_id] = incident
    return {
        "incident_id": incident_id,
        "status": "created",
        "message": f"Incident {incident_id} created successfully",
    }


# ── Tool 5: Get Incident Timeline ─────────────────────────────────────────────
@timed_tool
def get_incident_timeline(incident_id: str) -> dict:
    """Get the timeline of events for an incident."""
    incident_id = incident_id.upper()
    if incident_id not in INCIDENTS:
        # Return mock timeline for demo
        return {
            "incident_id": incident_id,
            "status": "resolved",
            "timeline": [
                {"timestamp": "2026-06-09T02:00:00Z", "event": "Alert fired: HighErrorRate on auth-service", "author": "prometheus"},
                {"timestamp": "2026-06-09T02:03:00Z", "event": "On-call paged", "author": "pagerduty"},
                {"timestamp": "2026-06-09T02:08:00Z", "event": "Engineer acknowledged", "author": "amar.singh"},
                {"timestamp": "2026-06-09T02:15:00Z", "event": "Root cause identified: bad deploy v2.3.1", "author": "amar.singh"},
                {"timestamp": "2026-06-09T02:18:00Z", "event": "Rollback initiated: kubectl rollout undo", "author": "amar.singh"},
                {"timestamp": "2026-06-09T02:22:00Z", "event": "Error rate returning to normal", "author": "prometheus"},
                {"timestamp": "2026-06-09T02:25:00Z", "event": "Incident resolved. Duration: 25min", "author": "amar.singh"},
            ],
        }
    return INCIDENTS[incident_id]


# ── Tool 6: Summarize Incident (LLM) ─────────────────────────────────────────
@timed_tool
def summarize_incident(incident_id: str, pipe=None) -> dict:
    """
    Generate an LLM summary of an incident.
    Uses local model if pipe provided, heuristic fallback otherwise.
    """
    timeline_data = get_incident_timeline(incident_id=incident_id)
    events = timeline_data.get("timeline", [])
    events_text = "\n".join(
        f"- {e['timestamp'][:19]}: {e['event']}" for e in events
    )

    if pipe is None:
        # Heuristic summary for CI/testing
        return {
            "incident_id": incident_id,
            "summary": f"Incident {incident_id} had {len(events)} timeline events. "
                      f"Started at {events[0]['timestamp'][:19] if events else 'unknown'}. "
                      f"Status: {timeline_data.get('status', 'unknown')}.",
            "model": "heuristic",
        }

    prompt = (
        f"<|im_start|>system\nYou are an SRE incident analyst. "
        f"Write a 3-sentence incident summary.<|im_end|>\n"
        f"<|im_start|>user\nIncident {incident_id} timeline:\n{events_text}\n"
        f"Write a concise summary covering: what happened, root cause, resolution.<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    try:
        output = pipe(prompt, return_full_text=False)[0]["generated_text"]
        summary = output.split("<|im_end|>")[0].strip()
        return {
            "incident_id": incident_id,
            "summary": summary,
            "model": "qwen2.5-0.5b",
        }
    except Exception as e:
        return {
            "incident_id": incident_id,
            "summary": f"Summary generation failed: {str(e)[:100]}",
            "model": "error",
        }


# ── Tool registry ─────────────────────────────────────────────────────────────
TOOLS = {
    "get_slo_status": {
        "fn": get_slo_status,
        "description": "Get SLO burn rate and status for a service. Args: service_name (str)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Service name e.g. auth-service"}
            },
            "required": ["service_name"],
        },
    },
    "get_runbook": {
        "fn": get_runbook,
        "description": "Fetch runbook steps for an alert. Args: alert_name (str)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alert_name": {"type": "string", "description": "Alert name e.g. HighErrorRate"}
            },
            "required": ["alert_name"],
        },
    },
    "query_alerts": {
        "fn": query_alerts,
        "description": "Query recent firing alerts. Args: severity ('all'|'critical'|'warning')",
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["all", "critical", "warning"], "default": "all"}
            },
        },
    },
    "create_incident": {
        "fn": create_incident,
        "description": "Create a new incident record. Args: title, severity, service, description",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                "service": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["title", "severity", "service"],
        },
    },
    "get_incident_timeline": {
        "fn": get_incident_timeline,
        "description": "Get timeline of events for an incident. Args: incident_id (str)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string", "description": "Incident ID e.g. INC-ABC123"}
            },
            "required": ["incident_id"],
        },
    },
    "summarize_incident": {
        "fn": summarize_incident,
        "description": "Generate LLM summary of an incident. Args: incident_id (str)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"}
            },
            "required": ["incident_id"],
        },
    },
}


def get_audit_log(n: int = 20) -> list[dict]:
    return AUDIT_LOG[-n:]
