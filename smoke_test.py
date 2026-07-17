#!/usr/bin/env python3
"""
Smoke test for Sales Agent — mandatory gate before starting any milestone.

Run this against an already-running `docker compose up --build` stack. It
does NOT start or stop containers itself; it only calls the running
services over HTTP, the same way a real client would, and reports
PASS/FAIL for each check the project's acceptance criteria require.

M0 checks (original six, unchanged):
    1.  Backend starts               (GET /api/v1/health)
    2.  Frontend starts               (GET http://localhost:5173)
    3.  /docs responds                (GET /docs)
    4.  Login succeeds                (POST /api/v1/auth/login with .env credentials)
    5.  Company creation              (POST /api/v1/companies)
    6.  Contact creation              (POST /api/v1/contacts)

M1.1 checks (Company Profile & Discovery Configuration):
    7.  Workspace Settings            (GET /api/v1/workspace-settings — auto-bootstraps on first call)
    8.  Company Profile creation      (POST /api/v1/company-profiles)
    9.  Default profile enforcement   (a second POST with is_default=true unsets the first)
    10. Product creation              (POST /api/v1/company-profiles/{id}/products)
    11. ICP Criteria creation         (POST /api/v1/company-profiles/{id}/icp-criteria)
    12. Knowledge Base entry creation (POST /api/v1/company-profiles/{id}/knowledge-base)

M1 checks (Buyer Discovery Engine):
    13. Search Templates reachable    (GET /api/v1/company-profiles/{id}/search-templates — system defaults seeded in 0003)
    14. Discovery Search creation     (POST /api/v1/company-profiles/{id}/discovery-searches, pinned to the ICP from step 11)
    15. Discovery Search run succeeds (POST .../discovery-searches/{id}/run using the manual_csv provider, synchronous)
    16. Prospects list succeeds       (GET /api/v1/company-profiles/{id}/prospects — the run's prospect is present)
    17. Prospect approve succeeds     (POST .../prospects/{id}/approve)

M2 checks (AI Research & Prospect Intelligence):
    18. Research Templates reachable       (GET .../research-templates — system defaults seeded in 0004)
    19. Research Request creation          (POST .../prospects/{id}/research-requests, pinned to a system template)
    20. Research Request run succeeds      (POST .../research-requests/{id}/run using the manual_document provider,
                                             synchronous — the deterministic AI stub analyzes the pasted text)
    21. Intelligence Snapshot created      (GET .../intelligence-snapshots/current — version 1, populated from the AI stub)
    22. Signals detected                   (GET .../signals — the pasted text's "expanding"/"hiring" keywords surfaced)
    23. Research Report generation succeeds (POST .../research-reports/generate, built FROM the current snapshot)

M3 checks (AI Personalization Engine):
    24. Personalization Templates reachable      (GET .../personalization-templates — system defaults seeded in 0005)
    25. Personalization Request creation         (POST .../prospects/{id}/personalization-requests, pinned to a system template)
    26. Personalization Request run succeeds     (POST .../personalization-requests/{id}/run — synchronous, reads the
                                                   Intelligence Snapshot/Signals/Recommendations from steps 20-23, no
                                                   external input of its own)
    27. Personalization Snapshot created         (GET .../personalization-snapshots/current — version 1, buyer_readiness
                                                   computed from the active Signals, at least primary+fallback strategies)
    28. Communication Strategy present           (all 8 axes populated on the current snapshot)

M4 checks (AI Outreach Generation Engine):
    29. Outreach Playbooks reachable             (GET .../outreach-playbooks — system default seeded in 0006)
    30. Prospect Contact creation succeeds        (POST .../prospects/{id}/contacts — outreach addresses a named
                                                   stakeholder, not the account, per the account-based-selling refinement)
    31. Outreach Request creation succeeds        (POST .../contacts/{id}/outreach-requests, pinned to the system
                                                   playbook + channel=email)
    32. Outreach Request run succeeds             (POST .../outreach-requests/{id}/run — synchronous, reads the current
                                                   Personalization Snapshot from steps 26-28, renders via the
                                                   deterministic EmailChannelProvider)
    33. Outreach Draft created                    (GET .../outreach-drafts/current?channel_key=email — version 1,
                                                   assembled subject+body present, evidence anchored to the primary
                                                   strategy)
    34. Outreach Draft approve succeeds           (POST .../outreach-drafts/{id}/approve — status becomes "approved")

Deliberately stdlib-only (urllib, not requests) so it runs on a bare
`python3` with nothing to install, on any machine that has Python.

Usage:
    python3 smoke_test.py
    make smoke-test

Exit code: 0 if all checks pass, 1 if any fail.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:5173"
ENV_FILE = Path(__file__).resolve().parent / ".env"

# Steps 1-3 poll for a bit, since the stack may still be finishing startup
# (wait-for-db retries, migrations, vite cold start) right after `up --build`.
POLL_ATTEMPTS = 10
POLL_DELAY_SECONDS = 2

_state: dict = {}
_results: list = []
TOTAL_STEPS = 34


def load_env(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def http_request(method: str, url: str, *, headers=None, json_body=None, form_body=None):
    headers = dict(headers or {})
    body = None
    if form_body is not None:
        body = "&".join(f"{k}={v}" for k, v in form_body.items()).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body is not None:
        body = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        # HTTPError still carries a real status + body — surface both
        # instead of treating every non-2xx as a connection failure.
        return exc.code, exc.read()


def poll(fn, attempts=POLL_ATTEMPTS, delay=POLL_DELAY_SECONDS):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - broad on purpose, this is a polling loop
            last_exc = exc
            if attempt < attempts:
                time.sleep(delay)
    raise last_exc


def step(name: str, fn) -> bool:
    label = f"[{len(_results) + 1}/{TOTAL_STEPS}] {name}"
    print(f"{label} ... ", end="", flush=True)
    try:
        detail = fn()
        print(f"PASS{f' ({detail})' if detail else ''}")
        _results.append((name, True, detail))
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL ({exc})")
        _results.append((name, False, str(exc)))
        return False


# --- the six checks -----------------------------------------------------


def check_backend_health() -> str:
    def attempt():
        status, raw = http_request("GET", f"{BACKEND_URL}/api/v1/health")
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        payload = json.loads(raw)
        if payload.get("status") != "ok":
            raise RuntimeError(f"unexpected payload {payload}")
        return "200 OK"

    return poll(attempt)


def check_frontend() -> str:
    def attempt():
        status, _ = http_request("GET", FRONTEND_URL)
        if status != 200:
            raise RuntimeError(f"unexpected status {status}")
        return "200 OK"

    return poll(attempt)


def check_docs() -> str:
    def attempt():
        status, _ = http_request("GET", f"{BACKEND_URL}/docs")
        if status != 200:
            raise RuntimeError(f"unexpected status {status}")
        return "200 OK"

    return poll(attempt)


def check_login() -> str:
    env = load_env(ENV_FILE)
    email = env.get("FIRST_ADMIN_EMAIL")
    password = env.get("FIRST_ADMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError(f"FIRST_ADMIN_EMAIL/FIRST_ADMIN_PASSWORD not found in {ENV_FILE}")

    def attempt():
        status, raw = http_request(
            "POST",
            f"{BACKEND_URL}/api/v1/auth/login",
            form_body={"username": email, "password": password},
        )
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        payload = json.loads(raw)
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"no access_token in response: {payload}")
        _state["token"] = token
        return f"authenticated as {email}"

    return poll(attempt)


def check_create_company() -> str:
    token = _state.get("token")
    if not token:
        raise RuntimeError("skipped — no access token from the login step")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/companies",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"name": "Smoke Test Textiles", "country": "Smoke Test Land"},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    company_id = payload.get("id")
    if not company_id:
        raise RuntimeError(f"no id in response: {payload}")
    _state["company_id"] = company_id
    return f"created company id={company_id}"


def check_create_contact() -> str:
    token = _state.get("token")
    company_id = _state.get("company_id")
    if not token or not company_id:
        raise RuntimeError("skipped — no token/company_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/contacts",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "company_id": company_id,
            "name": "Smoke Test Contact",
            "email": "smoke-test@example.com",
        },
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    contact_id = payload.get("id")
    if not contact_id:
        raise RuntimeError(f"no id in response: {payload}")
    return f"created contact id={contact_id}"


# --- M1.1 checks: Company Profile & Discovery Configuration -------------


def check_workspace_settings() -> str:
    token = _state.get("token")
    if not token:
        raise RuntimeError("skipped — no access token from the login step")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/workspace-settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if "id" not in payload or "date_format" not in payload:
        raise RuntimeError(f"unexpected payload shape: {payload}")
    return "workspace settings bootstrapped/fetched"


def check_create_company_profile() -> str:
    token = _state.get("token")
    if not token:
        raise RuntimeError("skipped — no access token from the login step")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"name": "Smoke Test Exports Pvt Ltd", "is_default": True},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    profile_id = payload.get("id")
    if not profile_id:
        raise RuntimeError(f"no id in response: {payload}")
    if payload.get("is_default") is not True:
        raise RuntimeError(f"expected is_default=True on first profile, got {payload.get('is_default')}")
    _state["company_profile_id"] = profile_id
    return f"created company profile id={profile_id}"


def check_default_profile_enforcement() -> str:
    token = _state.get("token")
    first_profile_id = _state.get("company_profile_id")
    if not token or not first_profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from the previous step")

    # Create a second profile also marked as default — the first one should
    # automatically be unset so at most one profile stays default per user.
    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"name": "Smoke Test Second Business", "is_default": True},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    second_payload = json.loads(raw)
    second_profile_id = second_payload.get("id")
    if second_payload.get("is_default") is not True:
        raise RuntimeError(f"expected is_default=True on second profile, got {second_payload.get('is_default')}")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{first_profile_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status} re-fetching first profile: {raw[:200]!r}")
    first_payload = json.loads(raw)
    if first_payload.get("is_default") is not False:
        raise RuntimeError(
            f"first profile still has is_default={first_payload.get('is_default')} "
            "after a second profile was marked default — enforcement is broken"
        )

    _state["company_profile_id"] = second_profile_id
    return "first profile's is_default auto-unset after second was marked default"


def check_create_product() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/products",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "name": "Smoke Test 300GSM Cotton Terry Towel",
            "category": "Home Textiles",
            "moq": "1000 pieces",
            # keywords/applications are what the M2 deterministic AI stub's
            # sales-intelligence pass matches against RawDocument text to
            # produce a product_fit Recommendation - see check_run_research_request.
            "keywords": ["terry towel", "cotton"],
        },
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    product_id = payload.get("id")
    if not product_id:
        raise RuntimeError(f"no id in response: {payload}")
    return f"created product id={product_id}"


def check_create_icp_criteria() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/icp-criteria",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"name": "Smoke Test Primary ICP"},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    icp_id = payload.get("id")
    if not icp_id:
        raise RuntimeError(f"no id in response: {payload}")
    if payload.get("version") != 1:
        raise RuntimeError(f"expected version=1 for the first ICP on this profile, got {payload.get('version')}")
    _state["icp_criteria_id"] = icp_id
    return f"created ICP criteria id={icp_id} version={payload.get('version')}"


def check_create_knowledge_base_entry() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/knowledge-base",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"title": "Smoke Test Entry", "content": "Created by smoke_test.py"},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    entry_id = payload.get("id")
    if not entry_id:
        raise RuntimeError(f"no id in response: {payload}")
    return f"created knowledge base entry id={entry_id}"


# --- M1 checks: Buyer Discovery Engine -----------------------------------


def check_search_templates() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/search-templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    templates = json.loads(raw)
    system_templates = [t for t in templates if t.get("is_system_default")]
    if not system_templates:
        raise RuntimeError(f"expected at least one system-seeded template, got: {templates}")
    _state["search_template_id"] = system_templates[0]["id"]
    return f"{len(templates)} template(s) visible, using system template id={system_templates[0]['id']}"


def check_create_discovery_search() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    template_id = _state.get("search_template_id")
    icp_id = _state.get("icp_criteria_id")
    if not all([token, profile_id, template_id, icp_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/search_template_id/icp_criteria_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/discovery-searches",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "name": "Smoke Test Search",
            "search_template_id": template_id,
            # Pinned rather than relying on an active ICP - the ICP created
            # in check_create_icp_criteria defaults to is_active=False, and
            # this test shouldn't depend on that default changing.
            "icp_criteria_id": icp_id,
            "provider_keys": ["manual_csv"],
        },
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    search_id = payload.get("id")
    if not search_id:
        raise RuntimeError(f"no id in response: {payload}")
    _state["discovery_search_id"] = search_id
    return f"created discovery search id={search_id}"


def check_run_discovery_search() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    search_id = _state.get("discovery_search_id")
    if not all([token, profile_id, search_id]):
        raise RuntimeError("skipped — no token/company_profile_id/discovery_search_id from earlier steps")

    # manual_csv needs its rows supplied via the search's query_spec at run
    # time - update the search with one test row, then run it.
    status, raw = http_request(
        "PUT",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/discovery-searches/{search_id}",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "query_spec": {
                "rows": [
                    {
                        "name": "Smoke Test Buyer GmbH",
                        "website": "https://smoke-test-buyer.example.com",
                        "country": "Germany",
                        "description": "Smoke test row for the manual_csv discovery provider.",
                    }
                ]
            }
        },
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status} updating search query_spec: {raw[:200]!r}")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/discovery-searches/{search_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") not in ("completed", "partially_completed"):
        raise RuntimeError(f"unexpected job status: {payload}")
    if payload.get("prospect_created_count", 0) < 1:
        raise RuntimeError(f"expected at least 1 new prospect, got: {payload}")
    return f"job {payload.get('id')} status={payload.get('status')} created {payload.get('prospect_created_count')} prospect(s)"


def check_list_prospects() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    prospects = json.loads(raw)
    if not prospects:
        raise RuntimeError("expected at least one prospect after running the discovery search")
    _state["prospect_id"] = prospects[0]["id"]
    return f"{len(prospects)} prospect(s) visible, using id={prospects[0]['id']}"


def check_approve_prospect() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    if not all([token, profile_id, prospect_id]):
        raise RuntimeError("skipped — no token/company_profile_id/prospect_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") != "approved":
        raise RuntimeError(f"expected status=approved, got: {payload}")
    return f"prospect {prospect_id} approved"


# --- M2 checks: AI Research & Prospect Intelligence ---------------------

# Deliberately hits the deterministic AI stub's known keyword vocabulary
# (see app/research/analysis/deterministic_stub.py): "manufacturer"/
# "ISO 9001" -> company_profile, "procurement team" -> buyer_profile,
# "expanding"/"new facility" and "hiring" -> business_signals, "terry
# towel" -> sales_intelligence (matches the product's keywords set in
# check_create_product).
RESEARCH_TEST_TEXT = (
    "We are a certified manufacturer with ISO 9001 certification. We are "
    "currently expanding with a new facility in Gujarat. Our procurement "
    "team and central buying office handle supplier onboarding, and we "
    "are hiring a new sourcing manager. Our product catalog includes "
    "cotton terry towel lines for the EU market."
)


def check_research_templates() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/research-templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    templates = json.loads(raw)
    system_templates = [t for t in templates if t.get("is_system_default")]
    if not system_templates:
        raise RuntimeError(f"expected at least one system-seeded research template, got: {templates}")
    _state["research_template_id"] = system_templates[0]["id"]
    return f"{len(templates)} template(s) visible, using system template id={system_templates[0]['id']}"


def check_create_research_request() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    template_id = _state.get("research_template_id")
    if not all([token, profile_id, prospect_id, template_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/research_template_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/research-requests",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"research_template_id": template_id},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    request_id = payload.get("id")
    if not request_id:
        raise RuntimeError(f"no id in response: {payload}")
    _state["research_request_id"] = request_id
    return f"created research request id={request_id}"


def check_run_research_request() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    request_id = _state.get("research_request_id")
    if not all([token, profile_id, prospect_id, request_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/research_request_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/research-requests/{request_id}/run",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"documents": [{"document_type": "pasted_text", "extracted_text": RESEARCH_TEST_TEXT}]},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") not in ("completed", "partially_completed"):
        raise RuntimeError(f"unexpected job status: {payload}")
    if payload.get("raw_document_count", 0) < 1:
        raise RuntimeError(f"expected at least 1 raw document, got: {payload}")
    return f"job {payload.get('id')} status={payload.get('status')} raw_document_count={payload.get('raw_document_count')}"


def check_intelligence_snapshot() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    if not all([token, profile_id, prospect_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/intelligence-snapshots/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("version") != 1:
        raise RuntimeError(f"expected version=1 for the first snapshot, got {payload.get('version')}")
    if payload.get("business_model") != "manufacturer":
        raise RuntimeError(f"expected business_model='manufacturer' from the AI stub, got: {payload.get('business_model')}")
    _state["intelligence_snapshot_id"] = payload.get("id")
    return f"snapshot id={payload.get('id')} version={payload.get('version')} business_model={payload.get('business_model')}"


def check_signals_detected() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    if not all([token, profile_id, prospect_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/signals",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    signals = json.loads(raw)
    signal_types = {s.get("signal_type") for s in signals}
    if "expansion" not in signal_types or "hiring" not in signal_types:
        raise RuntimeError(f"expected 'expansion' and 'hiring' signals from the AI stub, got types: {signal_types}")
    return f"{len(signals)} signal(s) detected: {sorted(signal_types)}"


def check_generate_research_report() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    if not all([token, profile_id, prospect_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/research-reports/generate",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    report_id = payload.get("id")
    if not report_id:
        raise RuntimeError(f"no id in response: {payload}")
    if not payload.get("content"):
        raise RuntimeError(f"expected non-empty content assembled from the intelligence snapshot, got: {payload}")
    return f"generated research report id={report_id}"


# --- M3 checks: AI Personalization Engine --------------------------------


def check_personalization_templates() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/personalization-templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    templates = json.loads(raw)
    system_templates = [t for t in templates if t.get("is_system_default")]
    if not system_templates:
        raise RuntimeError(f"expected at least one system-seeded personalization template, got: {templates}")
    _state["personalization_template_id"] = system_templates[0]["id"]
    return f"{len(templates)} template(s) visible, using system template id={system_templates[0]['id']}"


def check_create_personalization_request() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    template_id = _state.get("personalization_template_id")
    if not all([token, profile_id, prospect_id, template_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/personalization_template_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/personalization-requests",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"personalization_template_id": template_id},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    request_id = payload.get("id")
    if not request_id:
        raise RuntimeError(f"no id in response: {payload}")
    _state["personalization_request_id"] = request_id
    return f"created personalization request id={request_id}"


def check_run_personalization_request() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    request_id = _state.get("personalization_request_id")
    if not all([token, profile_id, prospect_id, request_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/personalization_request_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/personalization-requests/{request_id}/run",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") != "completed":
        raise RuntimeError(f"unexpected job status: {payload}")
    return f"job {payload.get('id')} status={payload.get('status')}"


def check_personalization_snapshot() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    if not all([token, profile_id, prospect_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/personalization-snapshots/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("version") != 1:
        raise RuntimeError(f"expected version=1 for the first snapshot, got {payload.get('version')}")
    # The research test text carries an "expansion" (importance=high) and a
    # "hiring" (importance=medium) signal, scoring 3 points under the
    # deterministic engine's thresholds - exactly the HIGH readiness band.
    if payload.get("buyer_readiness") != "high":
        raise RuntimeError(f"expected buyer_readiness='high' given the M2 test signals, got: {payload.get('buyer_readiness')}")
    ranks = {s["strategy_rank"] for s in payload.get("strategies", [])}
    # Only PRIMARY+FALLBACK are guaranteed - SECONDARY only appears when 2+
    # distinct-type Recommendations exist, which isn't guaranteed by the M2
    # smoke fixtures (only one product_fit recommendation is produced there).
    if not {"primary", "fallback"} <= ranks:
        raise RuntimeError(f"expected at least primary+fallback strategies, got ranks: {ranks}")
    _state["personalization_snapshot"] = payload
    return f"snapshot id={payload.get('id')} version=1 buyer_readiness=high ranks={sorted(ranks)}"


def check_communication_strategy() -> str:
    snapshot = _state.get("personalization_snapshot")
    if not snapshot:
        raise RuntimeError("skipped — no personalization_snapshot from the previous step")

    comm = snapshot.get("communication_strategy")
    if not comm:
        raise RuntimeError(f"expected a communication_strategy on the current snapshot, got: {snapshot}")
    required_axes = {
        "formality", "directness", "warmth", "technical_depth",
        "authority", "consultative_level", "urgency", "message_length",
    }
    missing = required_axes - set(k for k, v in comm.items() if v is not None)
    if missing:
        raise RuntimeError(f"communication_strategy missing values for axes: {missing}")
    return f"communication strategy present: formality={comm['formality']}, urgency={comm['urgency']}"


# --- M4 checks: AI Outreach Generation Engine ----------------------------


def check_outreach_playbooks() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/outreach-playbooks",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    playbooks = json.loads(raw)
    system_playbooks = [p for p in playbooks if p.get("is_system_default")]
    if not system_playbooks:
        raise RuntimeError(f"expected at least one system-seeded outreach playbook, got: {playbooks}")
    if not system_playbooks[0].get("blocks"):
        raise RuntimeError(f"expected the system playbook to have seeded blocks, got: {system_playbooks[0]}")
    _state["outreach_playbook_id"] = system_playbooks[0]["id"]
    return f"{len(playbooks)} playbook(s) visible, using system playbook id={system_playbooks[0]['id']}"


def check_create_prospect_contact() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    if not all([token, profile_id, prospect_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/contacts",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"name": "Smoke Test Buyer Contact", "role": "Procurement Manager", "email": "buyer@smoke-test-buyer.example.com"},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    contact_id = payload.get("id")
    if not contact_id:
        raise RuntimeError(f"no id in response: {payload}")
    _state["prospect_contact_id"] = contact_id
    return f"created prospect contact id={contact_id}"


def check_create_outreach_request() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    contact_id = _state.get("prospect_contact_id")
    playbook_id = _state.get("outreach_playbook_id")
    if not all([token, profile_id, prospect_id, contact_id, playbook_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/prospect_contact_id/outreach_playbook_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-requests",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"outreach_playbook_id": playbook_id, "channel_key": "email"},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    request_id = payload.get("id")
    if not request_id:
        raise RuntimeError(f"no id in response: {payload}")
    _state["outreach_request_id"] = request_id
    return f"created outreach request id={request_id}"


def check_run_outreach_request() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    contact_id = _state.get("prospect_contact_id")
    request_id = _state.get("outreach_request_id")
    if not all([token, profile_id, prospect_id, contact_id, request_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/prospect_contact_id/outreach_request_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-requests/{request_id}/run",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") != "completed":
        raise RuntimeError(f"unexpected job status: {payload}")
    return f"job {payload.get('id')} status={payload.get('status')}"


def check_outreach_draft() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    contact_id = _state.get("prospect_contact_id")
    if not all([token, profile_id, prospect_id, contact_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/prospect_contact_id from earlier steps")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts/current?channel_key=email",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("version") != 1:
        raise RuntimeError(f"expected version=1 for the first draft, got {payload.get('version')}")
    if not payload.get("is_current"):
        raise RuntimeError(f"expected is_current=True, got: {payload}")
    assembled = payload.get("current_content", {}).get("assembled", {})
    if not assembled.get("subject") or not assembled.get("body"):
        raise RuntimeError(f"expected a non-empty assembled subject+body, got: {assembled}")
    if not payload.get("evidence"):
        raise RuntimeError(f"expected at least one evidence entry anchored to the primary strategy, got: {payload.get('evidence')}")
    _state["outreach_draft_id"] = payload.get("id")
    return f"draft id={payload.get('id')} version=1 subject={assembled.get('subject')!r}"


def check_approve_outreach_draft() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    prospect_id = _state.get("prospect_id")
    contact_id = _state.get("prospect_contact_id")
    draft_id = _state.get("outreach_draft_id")
    if not all([token, profile_id, prospect_id, contact_id, draft_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/prospect_id/prospect_contact_id/outreach_draft_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-drafts/{draft_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") != "approved":
        raise RuntimeError(f"expected status=approved, got: {payload}")
    return f"draft {draft_id} approved"


def main() -> int:
    print("Sales Agent — M0 + M1.1 + M1 + M2 + M3 + M4 smoke test")
    print(f"backend={BACKEND_URL}  frontend={FRONTEND_URL}")
    print("(assumes `docker compose up --build` is already running)\n")

    all_passed = True
    all_passed &= step("Backend starts (/api/v1/health)", check_backend_health)
    all_passed &= step("Frontend starts", check_frontend)
    all_passed &= step("/docs responds", check_docs)
    all_passed &= step("Login succeeds", check_login)
    all_passed &= step("Company creation succeeds", check_create_company)
    all_passed &= step("Contact creation succeeds", check_create_contact)
    all_passed &= step("Workspace Settings reachable", check_workspace_settings)
    all_passed &= step("Company Profile creation succeeds", check_create_company_profile)
    all_passed &= step("Default Company Profile enforcement", check_default_profile_enforcement)
    all_passed &= step("Product creation succeeds", check_create_product)
    all_passed &= step("ICP Criteria creation succeeds", check_create_icp_criteria)
    all_passed &= step("Knowledge Base entry creation succeeds", check_create_knowledge_base_entry)
    all_passed &= step("Search Templates reachable", check_search_templates)
    all_passed &= step("Discovery Search creation succeeds", check_create_discovery_search)
    all_passed &= step("Discovery Search run succeeds", check_run_discovery_search)
    all_passed &= step("Prospects list succeeds", check_list_prospects)
    all_passed &= step("Prospect approve succeeds", check_approve_prospect)
    all_passed &= step("Research Templates reachable", check_research_templates)
    all_passed &= step("Research Request creation succeeds", check_create_research_request)
    all_passed &= step("Research Request run succeeds", check_run_research_request)
    all_passed &= step("Intelligence Snapshot created", check_intelligence_snapshot)
    all_passed &= step("Signals detected", check_signals_detected)
    all_passed &= step("Research Report generation succeeds", check_generate_research_report)
    all_passed &= step("Personalization Templates reachable", check_personalization_templates)
    all_passed &= step("Personalization Request creation succeeds", check_create_personalization_request)
    all_passed &= step("Personalization Request run succeeds", check_run_personalization_request)
    all_passed &= step("Personalization Snapshot created", check_personalization_snapshot)
    all_passed &= step("Communication Strategy present", check_communication_strategy)
    all_passed &= step("Outreach Playbooks reachable", check_outreach_playbooks)
    all_passed &= step("Prospect Contact creation succeeds", check_create_prospect_contact)
    all_passed &= step("Outreach Request creation succeeds", check_create_outreach_request)
    all_passed &= step("Outreach Request run succeeds", check_run_outreach_request)
    all_passed &= step("Outreach Draft created", check_outreach_draft)
    all_passed &= step("Outreach Draft approve succeeds", check_approve_outreach_draft)

    print("\n--- Summary ---")
    for name, passed, detail in _results:
        print(f"{'PASS' if passed else 'FAIL':4}  {name}")

    print()
    if all_passed:
        print(f"SMOKE TEST: PASS — all {TOTAL_STEPS} checks succeeded.")
    else:
        print("SMOKE TEST: FAIL — see the failing step(s) above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
