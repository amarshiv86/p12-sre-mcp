import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.tools import (
    get_slo_status, get_runbook, query_alerts,
    create_incident, get_incident_timeline,
    summarize_incident, get_audit_log,
)
from src.mcp_server import handle_request


class TestSLOTool:
    def test_known_service(self):
        result = get_slo_status(service_name="auth-service")
        assert "burn_rate" in result
        assert "status" in result
        assert result["status"] in ("OK", "ELEVATED", "WARNING", "CRITICAL")

    def test_unknown_service(self):
        result = get_slo_status(service_name="nonexistent")
        assert "error" in result
        assert "available_services" in result

    def test_critical_service_elevated(self):
        result = get_slo_status(service_name="auth-service")
        assert result["burn_rate"] > 1.0


class TestRunbookTool:
    def test_exact_match(self):
        result = get_runbook(alert_name="HighErrorRate")
        assert "immediate_steps" in result
        assert len(result["immediate_steps"]) > 0

    def test_fuzzy_match(self):
        result = get_runbook(alert_name="high error rate")
        assert "immediate_steps" in result

    def test_missing_runbook(self):
        result = get_runbook(alert_name="nonexistent_alert_xyz")
        assert "error" in result


class TestAlertsTool:
    def test_all_alerts(self):
        result = query_alerts(severity="all")
        assert result["total_firing"] > 0
        assert len(result["alerts"]) > 0

    def test_critical_filter(self):
        result = query_alerts(severity="critical")
        for alert in result["alerts"]:
            assert alert["severity"] == "critical"

    def test_alert_fields(self):
        result = query_alerts(severity="all")
        for alert in result["alerts"]:
            for field in ["id", "service", "alert", "severity", "summary"]:
                assert field in alert


class TestIncidentTools:
    def test_create_incident(self):
        result = create_incident(
            title="Test incident",
            severity="critical",
            service="auth-service",
        )
        assert "incident_id" in result
        assert result["incident_id"].startswith("INC-")
        assert result["status"] == "created"

    def test_get_timeline_demo(self):
        result = get_incident_timeline(incident_id="INC-DEMO01")
        assert "timeline" in result
        assert len(result["timeline"]) > 0

    def test_summarize_heuristic(self):
        result = summarize_incident(incident_id="INC-DEMO01", pipe=None)
        assert "summary" in result
        assert result["model"] == "heuristic"

    def test_create_then_retrieve(self):
        inc = create_incident(
            title="Test retrieve",
            severity="minor",
            service="test-svc",
        )
        inc_id = inc["incident_id"]
        timeline = get_incident_timeline(incident_id=inc_id)
        assert "timeline" in timeline


class TestAuditLog:
    def test_tool_calls_are_logged(self):
        initial_count = len(get_audit_log())
        get_slo_status(service_name="api-gateway")
        assert len(get_audit_log()) > initial_count

    def test_audit_entry_fields(self):
        get_slo_status(service_name="payment-service")
        log = get_audit_log(1)
        assert len(log) > 0
        entry = log[-1]
        for field in ["id", "timestamp", "tool", "latency_ms", "success"]:
            assert field in entry


class TestMCPProtocol:
    def test_initialize(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        response = handle_request(request)
        assert response["result"]["serverInfo"]["name"] == "sre-ops-mcp-server"
        assert "capabilities" in response["result"]

    def test_tools_list(self):
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        response = handle_request(request)
        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "get_slo_status" in tool_names
        assert "create_incident" in tool_names
        assert len(tools) == 6

    def test_tool_call(self):
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_slo_status",
                "arguments": {"service_name": "api-gateway"},
            },
        }
        response = handle_request(request)
        assert "result" in response
        content = response["result"]["content"][0]["text"]
        parsed = json.loads(content)
        assert "burn_rate" in parsed

    def test_unknown_tool_returns_error(self):
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
        response = handle_request(request)
        assert "error" in response

    def test_unknown_method_returns_error(self):
        request = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "unknown/method",
            "params": {},
        }
        response = handle_request(request)
        assert "error" in response

    def test_notification_returns_none(self):
        request = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        response = handle_request(request)
        assert response is None
