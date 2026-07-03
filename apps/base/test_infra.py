"""
Infrastructure test suite — the three cross-cutting features:

  1. Rate Limiting & Throttling   (Security)     -> HTTP 429 on excess
  2. Distributed Caching          (Performance)  -> per-tenant dashboard cache
  3. Centralized Error Tracking   (Monitoring)   -> Sentry tenant tagging

The headline test is `TestLoadSimulation` — it fires a large burst of calls at
a throttled endpoint and reports the distribution of response status codes
(how many 200/400 got through vs how many 429 got rate-limited).

Run the load report with output visible:

    pytest apps/base/test_throttling_caching_monitoring.py::TestLoadSimulation -s
"""
from collections import Counter
from uuid import uuid4
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.throttling import SimpleRateThrottle

from apps.base.errors import error_codes as codes

pytestmark = pytest.mark.django_db


# Shared helpers / fixtures

@pytest.fixture(autouse=True)
def _clear_cache():
    """
    DRF stores throttle counters in the `default` cache, which is a process-wide
    LocMemCache. Without clearing it between tests, throttle history (and the
    dashboard cache) leaks across tests and causes spurious 429s / stale reads.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture()
def set_rate(monkeypatch):
    """Temporarily override a DRF throttle rate (auto-reverted after the test)."""
    def _set(scope, rate):
        monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, rate)
    return _set


LOGIN_URL = "/api/v1/auth/login/"
AI_URL = "/api/v1/ai/risk-assessment/"
DASHBOARD_URL = "/api/v1/reports/dashboard/"


# 1. RATE LIMITING & THROTTLING  (Security)

class TestAnonThrottle:
    """AnonRateThrottle guards unauthenticated endpoints (by client IP)."""

    def test_requests_under_limit_are_allowed(self, api_client, tenant, set_rate):
        """With a 10/min limit, the first 10 anon calls are NOT throttled."""
        set_rate("anon", "10/minute")
        for i in range(10):
            r = api_client.post(LOGIN_URL, {"email": "x@y.z", "password": "nope"})
            assert r.status_code != status.HTTP_429_TOO_MANY_REQUESTS, f"throttled early at #{i+1}"

    def test_crossing_limit_returns_429(self, api_client, tenant, set_rate):
        """The 11th call in the window is rejected with 429."""
        set_rate("anon", "10/minute")
        for _ in range(10):
            api_client.post(LOGIN_URL, {"email": "x@y.z", "password": "nope"})
        r = api_client.post(LOGIN_URL, {"email": "x@y.z", "password": "nope"})
        assert r.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_429_body_uses_unified_error_shape(self, api_client, tenant, set_rate):
        """A throttled response is normalized to {"message", "code"} like every other error."""
        set_rate("anon", "3/minute")
        last = None
        for _ in range(5):
            last = api_client.post(LOGIN_URL, {"email": "x@y.z", "password": "nope"})
        assert last.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert set(last.data.keys()) == {"message", "code"}
        assert "throttled" in last.data["message"].lower()
        # 429 isn't in the status->code map, so it flattens to NO_CODE (0).
        assert last.data["code"] == codes.NO_CODE

    def test_429_sets_retry_after_header(self, api_client, tenant, set_rate):
        """DRF advertises when the client may retry via the Retry-After header."""
        set_rate("anon", "3/minute")
        last = None
        for _ in range(5):
            last = api_client.post(LOGIN_URL, {"email": "x@y.z", "password": "nope"})
        assert last.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in last.headers
        assert int(last.headers["Retry-After"]) > 0


class TestAIScopedThrottle:
    """The AI endpoint has its own, much stricter `ai_requests` scope (50/day)."""

    def _payload(self):
        return {"action": "APPROVE_REQUEST", "request_id": str(uuid4())}

    def test_ai_scope_throttles_independently(self, admin_api_client, tenant, set_rate):
        """With ai_requests=3/day, the 4th AI call is throttled even though the
        user is far below the global user limit."""
        set_rate("ai_requests", "3/day")
        codes_seen = []
        with patch("apps.ai.views.RiskAssessmentService") as svc:
            svc.assess_request.return_value = {
                "risk_score": 10, "risk_level": "LOW",
                "recommendation": "APPROVE", "reasoning": "ok",
            }
            for _ in range(5):
                r = admin_api_client.post(AI_URL, self._payload(), format="json")
                codes_seen.append(r.status_code)

        assert codes_seen.count(status.HTTP_200_OK) == 3
        assert codes_seen.count(status.HTTP_429_TOO_MANY_REQUESTS) == 2


# 2. DISTRIBUTED CACHING  (Performance)

class TestDashboardCaching:
    """DashboardView caches expensive aggregate stats per tenant for 15 min."""

    def test_first_call_populates_cache(self, admin_api_client, tenant):
        from django.core.cache import cache
        assert cache.get(f"dashboard_stats_{tenant.schema_name}") is None
        r = admin_api_client.get(DASHBOARD_URL)
        assert r.status_code == status.HTTP_200_OK
        assert cache.get(f"dashboard_stats_{tenant.schema_name}") is not None

    def test_second_call_is_served_stale_from_cache(
        self, admin_api_client, tenant, asset_factory, category
    ):
        """A row created AFTER the first (cached) call is NOT reflected until the
        cache expires — proving the second response came from cache, not the DB."""
        first = admin_api_client.get(DASHBOARD_URL)
        total_before = first.data["assets"]["total"]

        asset_factory(name="Fresh Laptop", category=category)

        second = admin_api_client.get(DASHBOARD_URL)
        assert second.data["assets"]["total"] == total_before

    def test_cache_clear_forces_recompute(
        self, admin_api_client, tenant, asset_factory, category
    ):
        from django.core.cache import cache
        first = admin_api_client.get(DASHBOARD_URL)
        total_before = first.data["assets"]["total"]

        asset_factory(name="Another Laptop", category=category)
        cache.clear()  # simulate expiry / invalidation

        third = admin_api_client.get(DASHBOARD_URL)
        assert third.data["assets"]["total"] == total_before + 1

    def test_cache_key_is_tenant_scoped(self, admin_api_client, tenant):
        """The cache key is namespaced by schema so tenants never see each other's stats."""
        from django.core.cache import cache
        admin_api_client.get(DASHBOARD_URL)
        assert cache.get(f"dashboard_stats_{tenant.schema_name}") is not None
        assert cache.get("dashboard_stats_some_other_tenant") is None


# 3. CENTRALIZED ERROR TRACKING  (Monitoring)

class TestSentryMonitoring:
    """Sentry is wired for per-tenant error attribution."""

    def test_request_tags_the_active_tenant(self, api_client, tenant):
        """Every request through the tenant middleware tags Sentry with the schema,
        so captured errors are attributable to an organization."""
        with patch("sentry_sdk.set_tag") as set_tag:
            api_client.get("/api/v1/assets/")
        set_tag.assert_any_call("tenant", tenant.schema_name)

    def test_sentry_sdk_is_installed(self):
        """The monitoring dependency is importable (guards against missing install)."""
        import sentry_sdk
        assert hasattr(sentry_sdk, "init")
        assert hasattr(sentry_sdk, "set_tag")


# LOAD SIMULATION — "which response types do we see under heavy traffic?"

class TestLoadSimulation:
    """
    Fire a large burst of calls at a throttled endpoint and report the
    distribution of HTTP status codes. Run with `-s` to see the printed report.
    """

    def test_status_code_distribution_under_burst(self, api_client, tenant, set_rate):
        BURST = 60
        LIMIT = 20
        set_rate("anon", f"{LIMIT}/minute")

        distribution = Counter()
        sample_429 = None
        for _ in range(BURST):
            r = api_client.post(LOGIN_URL, {"email": "x@y.z", "password": "nope"})
            distribution[r.status_code] += 1
            if r.status_code == status.HTTP_429_TOO_MANY_REQUESTS and sample_429 is None:
                sample_429 = r

        allowed = distribution[status.HTTP_400_BAD_REQUEST]
        throttled = distribution[status.HTTP_429_TOO_MANY_REQUESTS]

        print("\n" + "=" * 58)
        print(f" LOAD SIMULATION — {BURST} calls, anon limit = {LIMIT}/minute")
        print("=" * 58)
        for code in sorted(distribution):
            label = {
                400: "400 Bad Request  (allowed → invalid creds)",
                429: "429 Too Many Requests  (RATE LIMITED)",
            }.get(code, f"{code}")
            print(f"   {label:<48} : {distribution[code]:>3}")
        print("-" * 58)
        print(f"   Allowed through : {allowed}")
        print(f"   Rate limited    : {throttled}")
        if sample_429 is not None:
            print(f"   Retry-After     : {sample_429.headers.get('Retry-After')}s")
            print(f"   429 body        : {dict(sample_429.data)}")
        print("=" * 58)

        # Exactly LIMIT get through; the rest are rejected.
        assert allowed == LIMIT
        assert throttled == BURST - LIMIT
        assert allowed + throttled == BURST
