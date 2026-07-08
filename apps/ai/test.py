"""
Test Suite for AI Risk Assessment module.

Covers:
- AI endpoint access control (only HR/Admin)
- Validation of action + required IDs
- Mock response fallback when no API key
"""
import io
import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest
from rest_framework import status

from apps.ai.services import RiskAssessmentService
from apps.base.errors import AFValidationError, error_codes

pytestmark = pytest.mark.django_db


def _gemini_body(payload_dict):
    """Build a Gemini API JSON envelope whose text part is `payload_dict` as JSON."""
    return {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps(payload_dict)}]}}
        ]
    }


def _fake_urlopen_returning(body_dict):
    """Return a context-manager mock whose .read() yields json.dumps(body_dict)."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(body_dict).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


class TestAIEndpointAccess:
    """AI risk assessment endpoint access."""

    url = "/api/v1/ai/risk-assessment/"

    def test_unauthenticated_cannot_access_ai(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.post(self.url, data={
            "action": "APPROVE_REQUEST",
        })
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_cannot_access_ai(self, employee_api_client):
        """EMPLOYEE → 403."""
        response = employee_api_client.post(self.url, data={
            "action": "APPROVE_REQUEST",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_action_rejected(self, hr_api_client):
        """Invalid action type → 400."""
        response = hr_api_client.post(self.url, data={
            "action": "HACK_SYSTEM",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_request_requires_request_id(self, hr_api_client):
        """APPROVE_REQUEST without request_id → 400."""
        response = hr_api_client.post(self.url, data={
            "action": "APPROVE_REQUEST",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_allocate_asset_requires_both_ids(self, hr_api_client):
        """ALLOCATE_ASSET without employee_id/asset_id → 400."""
        response = hr_api_client.post(self.url, data={
            "action": "ALLOCATE_ASSET",
            "employee_id": "",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestRiskAssessmentContextBuilding:
    """assess_request / assess_allocation gather context and delegate to _call_llm."""

    def test_assess_request_not_found_raises(self, tenant):
        """Unknown request id → AFValidationError(RECORD_NOT_FOUND)."""
        import uuid
        with pytest.raises(AFValidationError) as exc:
            RiskAssessmentService.assess_request(uuid.uuid4())
        assert exc.value.detail["code"] == error_codes.RECORD_NOT_FOUND

    def test_assess_allocation_not_found_raises(self, tenant, asset):
        """Unknown employee id → AFValidationError(RECORD_NOT_FOUND)."""
        import uuid
        with pytest.raises(AFValidationError) as exc:
            RiskAssessmentService.assess_allocation(uuid.uuid4(), asset.id)
        assert exc.value.detail["code"] == error_codes.RECORD_NOT_FOUND

    def test_assess_request_builds_context_and_calls_llm(
        self, asset_request_factory, employee, category,
        allocation_factory, asset, incident_factory,
    ):
        """assess_request should pull employee assets + incidents into the
        context string passed to _call_llm, and return its result."""
        # Give the employee an active allocation and a past incident.
        allocation_factory(asset=asset, employee=employee)
        incident_factory(reported_by=employee, title="Broke laptop")
        req = asset_request_factory(requested_by=employee, category=category)

        with patch.object(
            RiskAssessmentService, "_call_llm", return_value={"risk_score": 5}
        ) as m:
            result = RiskAssessmentService.assess_request(req.id)

        assert result == {"risk_score": 5}
        context = m.call_args.args[0]
        assert "Action: Approve Asset Request" in context
        assert employee.get_full_name() in context
        assert asset.name in context
        assert "Broke laptop" in context

    def test_assess_allocation_builds_context_and_calls_llm(
        self, employee, asset, allocation_factory, asset_factory,
        category, incident_factory,
    ):
        """assess_allocation builds an 'Allocate Asset' context and calls _call_llm."""
        other_asset = asset_factory(name="Existing Monitor", category=category)
        allocation_factory(asset=other_asset, employee=employee)
        incident_factory(asset=asset, reported_by=employee, title="Screen crack")

        with patch.object(
            RiskAssessmentService, "_call_llm", return_value={"risk_score": 42}
        ) as m:
            result = RiskAssessmentService.assess_allocation(employee.id, asset.id)

        assert result == {"risk_score": 42}
        context = m.call_args.args[0]
        assert "Action: Manually Allocate Asset to Employee" in context
        assert asset.name in context
        assert "Existing Monitor" in context


class TestCallLLM:
    """_call_llm: key handling, success path, and every fallback branch."""

    CANNED = {
        "risk_score": 20,
        "risk_level": "LOW",
        "recommendation": "APPROVE",
        "reasoning": "1. Safe",
    }

    def test_no_api_key_uses_mock(self, monkeypatch):
        """Without GEMINI_API_KEY, _call_llm delegates to the deterministic mock."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        result = RiskAssessmentService._call_llm("Action: test\n")
        assert set(result.keys()) == {
            "risk_score", "risk_level", "recommendation", "reasoning"
        }
        assert "mock AI response" in result["reasoning"]
        assert 0 <= result["risk_score"] <= 100

    def test_success_path_parses_gemini_response(self, monkeypatch):
        """A well-formed Gemini envelope is unwrapped to the inner JSON."""
        monkeypatch.setenv("GEMINI_API_KEY", "  'secret-key'  ")
        with patch(
            "apps.ai.services.urllib.request.urlopen",
            return_value=_fake_urlopen_returning(_gemini_body(self.CANNED)),
        ) as m:
            result = RiskAssessmentService._call_llm("ctx")
        assert result == self.CANNED
        # The key was stripped of quotes/whitespace before being placed in the URL.
        called_req = m.call_args.args[0]
        assert "key=secret-key" in called_req.full_url

    def test_httperror_returns_review_fallback(self, monkeypatch):
        """An HTTP 4xx/5xx from Gemini → MEDIUM/REVIEW fallback, no raise."""
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        err = urllib.error.HTTPError(
            url="http://x", code=429, msg="Too Many",
            hdrs=None, fp=io.BytesIO(b"quota exceeded"),
        )
        with patch(
            "apps.ai.services.urllib.request.urlopen", side_effect=err
        ):
            result = RiskAssessmentService._call_llm("ctx")
        assert result["recommendation"] == "REVIEW"
        assert result["risk_level"] == "MEDIUM"
        assert "HTTP 429" in result["reasoning"]

    def test_urlerror_returns_review_fallback(self, monkeypatch):
        """A network URLError → MEDIUM/REVIEW fallback."""
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        with patch(
            "apps.ai.services.urllib.request.urlopen",
            side_effect=urllib.error.URLError("dns down"),
        ):
            result = RiskAssessmentService._call_llm("ctx")
        assert result["recommendation"] == "REVIEW"
        assert "network failure" in result["reasoning"]

    def test_timeout_returns_review_fallback(self, monkeypatch):
        """A socket TimeoutError → MEDIUM/REVIEW fallback with timeout message."""
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        with patch(
            "apps.ai.services.urllib.request.urlopen",
            side_effect=TimeoutError(),
        ):
            result = RiskAssessmentService._call_llm("ctx")
        assert result["recommendation"] == "REVIEW"
        assert "timed out" in result["reasoning"]

    def test_mock_llm_high_score_maps_to_deny(self, monkeypatch):
        """The mock maps high scores to HIGH/DENY (branch coverage)."""
        with patch("apps.ai.services.random.randint", return_value=85):
            out = RiskAssessmentService._mock_llm("ctx")
        assert out["risk_level"] == "HIGH"
        assert out["recommendation"] == "DENY"

    def test_mock_llm_medium_score_maps_to_review(self):
        """Mid-range scores map to MEDIUM/REVIEW."""
        with patch("apps.ai.services.random.randint", return_value=50):
            out = RiskAssessmentService._mock_llm("ctx")
        assert out["risk_level"] == "MEDIUM"
        assert out["recommendation"] == "REVIEW"

    def test_mock_llm_low_score_maps_to_approve(self):
        """Low scores map to LOW/APPROVE."""
        with patch("apps.ai.services.random.randint", return_value=10):
            out = RiskAssessmentService._mock_llm("ctx")
        assert out["risk_level"] == "LOW"
        assert out["recommendation"] == "APPROVE"


class TestAIEndpointServiceIntegration:
    """The view wires action → service; assert the happy paths return the AI body."""

    url = "/api/v1/ai/risk-assessment/"

    def test_approve_request_returns_ai_response(
        self, hr_api_client, asset_request_factory, employee, category
    ):
        req = asset_request_factory(requested_by=employee, category=category)
        canned = {
            "risk_score": 12, "risk_level": "LOW",
            "recommendation": "APPROVE", "reasoning": "ok",
        }
        with patch.object(
            RiskAssessmentService, "assess_request", return_value=canned
        ) as m:
            response = hr_api_client.post(
                self.url,
                data={"action": "APPROVE_REQUEST", "request_id": str(req.id)},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["recommendation"] == "APPROVE"
        m.assert_called_once()

    def test_allocate_asset_returns_ai_response(
        self, hr_api_client, employee, asset
    ):
        canned = {
            "risk_score": 60, "risk_level": "MEDIUM",
            "recommendation": "REVIEW", "reasoning": "check",
        }
        with patch.object(
            RiskAssessmentService, "assess_allocation", return_value=canned
        ) as m:
            response = hr_api_client.post(
                self.url,
                data={
                    "action": "ALLOCATE_ASSET",
                    "employee_id": str(employee.id),
                    "asset_id": str(asset.id),
                },
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["recommendation"] == "REVIEW"
        m.assert_called_once()
        emp_arg, asset_arg = m.call_args.args
        assert str(emp_arg) == str(employee.id)
        assert str(asset_arg) == str(asset.id)
