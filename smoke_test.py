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
    15. Discovery Search run succeeds (POST .../discovery-searches/{id}/run — ASYNCHRONOUS since M8.8: returns 202/
                                        "queued", no DiscoveryJob yet. This step polls
                                        GET .../discovery-jobs?discovery_search_id={id} - the same independent-worker
                                        poll-and-wait pattern the M5 section below uses for the `worker` container,
                                        applied here to the Workflow Engine's Event Dispatcher + Step Runner - until
                                        a job appears and reaches a terminal status. Fixed post-M2-Phase-1a: this
                                        step previously still asserted the pre-M8.8 synchronous contract (HTTP 201
                                        with an inline job result), which had been silently wrong since M8.8 shipped
                                        and only surfaced when the full smoke test was run again after Phase 1a.)
    16. Prospects list succeeds       (GET /api/v1/company-profiles/{id}/prospects — the run's prospect is present)
    17. Prospect approve succeeds     (POST .../prospects/{id}/approve)

M2 checks (AI Research & Prospect Intelligence):
    18. Research Templates reachable       (GET .../research-templates — system defaults seeded in 0004)
    19. Research Request creation          (POST .../prospects/{id}/research-requests, pinned to a system template)
    20. Research Request run succeeds      (POST .../research-requests/{id}/run — ASYNCHRONOUS since M8.13, same
                                             202/"queued" + poll-until-terminal contract as step 15, applied to
                                             GET .../research-jobs?research_request_id={id}. The deterministic AI
                                             stub analyzes the pasted text once the job actually runs.)
    21. Intelligence Snapshot created      (GET .../intelligence-snapshots/current — version 1, populated from the AI stub)
    22. Signals detected                   (GET .../signals — the pasted text's "expanding"/"hiring" keywords surfaced)
    23. Research Report generation succeeds (POST .../research-reports/generate, built FROM the current snapshot)

M3 checks (AI Personalization Engine):
    24. Personalization Templates reachable      (GET .../personalization-templates — system defaults seeded in 0005)
    25. Personalization Request creation         (POST .../prospects/{id}/personalization-requests, pinned to a system template)
    26. Personalization Request run succeeds     (POST .../personalization-requests/{id}/run — ASYNCHRONOUS since
                                                   M8.14, same 202/"queued" + poll-until-terminal contract as step
                                                   15, applied to GET .../personalization-jobs?
                                                   personalization_request_id={id}. Reads the Intelligence Snapshot/
                                                   Signals/Recommendations from steps 20-23 once it actually runs; no
                                                   external input of its own.)
    27. Personalization Snapshot created         (GET .../personalization-snapshots/current — version 1, buyer_readiness
                                                   computed from the active Signals, at least primary+fallback strategies)
    28. Communication Strategy present           (all 8 axes populated on the current snapshot)

M4 checks (AI Outreach Generation Engine):
    29. Outreach Playbooks reachable             (GET .../outreach-playbooks — system default seeded in 0006)
    30. Prospect Contact creation succeeds        (POST .../prospects/{id}/contacts — outreach addresses a named
                                                   stakeholder, not the account, per the account-based-selling refinement)
    31. Outreach Request creation succeeds        (POST .../contacts/{id}/outreach-requests, pinned to the system
                                                   playbook + channel=email)
    32. Outreach Request run succeeds             (POST .../outreach-requests/{id}/run — ASYNCHRONOUS since M8.15,
                                                   same 202/"queued" + poll-until-terminal contract as step 15,
                                                   applied to GET .../outreach-jobs?outreach_request_id={id}. Reads
                                                   the current Personalization Snapshot from steps 26-28 and renders
                                                   via the deterministic EmailChannelProvider once it actually runs.)
    33. Outreach Draft created                    (GET .../outreach-drafts/current?channel_key=email — version 1,
                                                   assembled subject+body present, evidence anchored to the primary
                                                   strategy)
    34. Outreach Draft approve succeeds           (POST .../outreach-drafts/{id}/approve — status becomes "approved")

M5 checks (Outreach Delivery Engine) — the one section here that is NOT
purely synchronous-in-request: steps 41 and 44 poll and wait for the
independent `worker` container (see docker-compose.yml) to actually claim
and dispatch a queue item on its own clock. No real Gmail/Outlook
credentials exist in this environment (or in any CI environment — this is
a structural limitation, not a sandbox one), so these steps deliberately
exercise dispatch_service's deterministic, credential-free failure path
(see dispatch_service.dispatch(): no usable ProviderConnection -> a real,
permanent, assertable FAILED outcome) rather than a real send. That
failure path is the one place a genuinely unmocked, full-stack proof of
"the worker is alive and wired correctly end-to-end" is possible without
a human completing a real OAuth consent screen.
    35. Connectable providers reachable          (GET /delivery/providers — may legitimately be an empty list if no
                                                   OAuth client id/secret is configured in this environment)
    36. SendingProfile creation succeeds          (POST .../sending-profiles — provider_key="gmail", no
                                                   provider_connection_id, sending window widened to cover all of UTC
                                                   today so scheduling doesn't depend on wall-clock time)
    37. SendingProfile update succeeds            (PUT .../sending-profiles/{id} — label change)
    38. Available drafts include the M4 draft     (GET .../delivery-campaigns/available-drafts — the approved,
                                                   not-yet-queued draft from step 34 is present)
    39. DeliveryCampaign creation succeeds        (POST .../delivery-campaigns — one queue item created in QUEUED)
    40. DeliveryCampaign schedule succeeds        (POST .../schedule — campaign becomes ACTIVE, queue item becomes
                                                   SCHEDULED with scheduled_send_at ~= now)
    41. Worker dispatches to a deterministic FAILED (poll .../queue-items/{id} up to ~75s for status="failed" with
                                                   the exact "no usable ProviderConnection" error — the end-to-end
                                                   pipeline proof described above)
    42. Available drafts include the draft again  (FAILED is not an "actively queued" status — the draft is released
                                                   back to the picker)
    43. Queue item Retry Now succeeds             (POST .../queue-items/{id}/retry — status back to SCHEDULED)
    44. Worker dispatches the retry to FAILED too (second independent worker tick, proving retry_now's SCHEDULED
                                                   item is picked up the same as an original one; attempt_count==2)
    45. Campaign pause/resume/cancel lifecycle    (a second campaign against the now-released draft, left
                                                   deliberately un-scheduled so this has zero race window against the
                                                   worker: DRAFT -> PAUSED -> ACTIVE -> CANCELLED, cascading to the
                                                   queue item)
    46. Queue item Cancel succeeds                (a third campaign against the released draft; POST
                                                   .../queue-items/{id}/cancel directly, distinct from the campaign-
                                                   level cascade cancel in step 45)

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

# Shared by five independent-worker wait patterns, all materially longer/
# coarser-grained than the HTTP/DB-readiness polling above:
#   - M1 step 15, M2 step 20, M3 step 26, and M4 step 32 each wait for
#     the Workflow Engine's Event Dispatcher + Step Runner workers
#     (their own poll intervals, WORKFLOW_EVENT_DISPATCHER_POLL_INTERVAL_SECONDS/
#     WORKFLOW_STEP_RUNNER_POLL_INTERVAL_SECONDS) to turn a queued
#     *_run_requested event into a completed Discovery/Research/
#     Personalization/OutreachJob, respectively - all four /run
#     endpoints share the identical M8.8-established async contract
#     (202/"queued", poll the corresponding *-jobs list endpoint until
#     terminal), so all four checks share this same poll budget.
#   - M5 steps 41/44 wait for the independent `worker` container's own
#     poll loop (DELIVERY_WORKER_POLL_INTERVAL_SECONDS, 15s by default)
#     to notice and dispatch a queue item.
WORKER_POLL_ATTEMPTS = 25
WORKER_POLL_DELAY_SECONDS = 3

_state: dict = {}
_results: list = []
TOTAL_STEPS = 46


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

    # M8.8: /run is asynchronous - it only validates the search and
    # publishes a trigger event, returning 202/"queued" with no
    # DiscoveryJob yet (see DiscoverySearchRunQueued's own docstring in
    # app/schemas/discovery_search.py). Real execution happens whenever
    # the Event Dispatcher and Step Runner workers next poll. This used
    # to assert the pre-M8.8 synchronous contract (HTTP 201 with an
    # inline job result) - fixed here, not in the API or the workers.
    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/discovery-searches/{search_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 202:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    queued_payload = json.loads(raw)
    if queued_payload.get("status") != "queued":
        raise RuntimeError(f"expected status='queued' from the async /run response, got: {queued_payload}")

    # Poll for the resulting DiscoveryJob to appear and reach a terminal
    # status - same poll-and-wait pattern as the M5 worker checks below
    # (WORKER_POLL_ATTEMPTS/WORKER_POLL_DELAY_SECONDS), applied here to
    # the Workflow Engine's own two independent workers instead of the
    # Delivery `worker` container.
    def attempt():
        status, raw = http_request(
            "GET",
            f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/discovery-jobs?discovery_search_id={search_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        jobs = json.loads(raw)
        if not jobs:
            raise RuntimeError(
                "no DiscoveryJob yet - Event Dispatcher/Step Runner haven't picked up the run request yet"
            )
        job = jobs[0]  # list_discovery_jobs orders by created_at desc
        if job.get("status") not in ("completed", "partially_completed", "failed", "cancelled"):
            raise RuntimeError(f"DiscoveryJob {job.get('id')} still status={job.get('status')!r}")
        return job

    job = poll(attempt, attempts=WORKER_POLL_ATTEMPTS, delay=WORKER_POLL_DELAY_SECONDS)
    if job.get("status") not in ("completed", "partially_completed"):
        raise RuntimeError(f"unexpected terminal job status: {job}")
    if job.get("prospect_created_count", 0) < 1:
        raise RuntimeError(f"expected at least 1 new prospect, got: {job}")
    _state["discovery_job_id"] = job.get("id")
    return (
        f"job {job.get('id')} status={job.get('status')} created "
        f"{job.get('prospect_created_count')} prospect(s) (queued -> polled to completion)"
    )


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

    # M8.13: /run is asynchronous - exact mirror of Discovery's M8.8
    # change (see check_run_discovery_search's own comment above). 202/
    # "queued" with no ResearchJob yet; real execution happens on the
    # Event Dispatcher/Step Runner workers' next poll tick.
    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/research-requests/{request_id}/run",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"documents": [{"document_type": "pasted_text", "extracted_text": RESEARCH_TEST_TEXT}]},
    )
    if status != 202:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    queued_payload = json.loads(raw)
    if queued_payload.get("status") != "queued":
        raise RuntimeError(f"expected status='queued' from the async /run response, got: {queued_payload}")

    # Poll for the resulting ResearchJob - same pattern as
    # check_run_discovery_search, applied to research-jobs instead of
    # discovery-jobs.
    def attempt():
        status, raw = http_request(
            "GET",
            f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/research-jobs?research_request_id={request_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        jobs = json.loads(raw)
        if not jobs:
            raise RuntimeError(
                "no ResearchJob yet - Event Dispatcher/Step Runner haven't picked up the run request yet"
            )
        job = jobs[0]  # list_research_jobs orders by created_at desc
        if job.get("status") not in ("completed", "partially_completed", "failed", "cancelled"):
            raise RuntimeError(f"ResearchJob {job.get('id')} still status={job.get('status')!r}")
        return job

    job = poll(attempt, attempts=WORKER_POLL_ATTEMPTS, delay=WORKER_POLL_DELAY_SECONDS)
    if job.get("status") not in ("completed", "partially_completed"):
        raise RuntimeError(f"unexpected terminal job status: {job}")
    if job.get("raw_document_count", 0) < 1:
        raise RuntimeError(f"expected at least 1 raw document, got: {job}")
    return (
        f"job {job.get('id')} status={job.get('status')} "
        f"raw_document_count={job.get('raw_document_count')} (queued -> polled to completion)"
    )


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

    # M8.14: /run is asynchronous - exact mirror of Discovery's M8.8
    # change. 202/"queued" with no PersonalizationJob yet.
    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/personalization-requests/{request_id}/run",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 202:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    queued_payload = json.loads(raw)
    if queued_payload.get("status") != "queued":
        raise RuntimeError(f"expected status='queued' from the async /run response, got: {queued_payload}")

    # Poll for the resulting PersonalizationJob - same pattern as
    # check_run_discovery_search, applied to personalization-jobs.
    # PersonalizationJobStatus has no PARTIALLY_COMPLETED value (unlike
    # Discovery/Research) - only completed/failed/cancelled are terminal.
    def attempt():
        status, raw = http_request(
            "GET",
            f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/personalization-jobs"
            f"?personalization_request_id={request_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        jobs = json.loads(raw)
        if not jobs:
            raise RuntimeError(
                "no PersonalizationJob yet - Event Dispatcher/Step Runner haven't picked up the run request yet"
            )
        job = jobs[0]  # list_personalization_jobs orders by created_at desc
        if job.get("status") not in ("completed", "failed", "cancelled"):
            raise RuntimeError(f"PersonalizationJob {job.get('id')} still status={job.get('status')!r}")
        return job

    job = poll(attempt, attempts=WORKER_POLL_ATTEMPTS, delay=WORKER_POLL_DELAY_SECONDS)
    if job.get("status") != "completed":
        raise RuntimeError(f"unexpected terminal job status: {job}")
    return f"job {job.get('id')} status={job.get('status')} (queued -> polled to completion)"


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

    # M8.15: /run is asynchronous - exact mirror of Discovery's M8.8
    # change. 202/"queued" with no OutreachJob yet.
    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/prospects/{prospect_id}/contacts/{contact_id}/outreach-requests/{request_id}/run",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 202:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    queued_payload = json.loads(raw)
    if queued_payload.get("status") != "queued":
        raise RuntimeError(f"expected status='queued' from the async /run response, got: {queued_payload}")

    # Poll for the resulting OutreachJob - same pattern as
    # check_run_discovery_search, applied to outreach-jobs.
    # OutreachJobStatus has no PARTIALLY_COMPLETED value either - only
    # completed/failed/cancelled are terminal.
    def attempt():
        status, raw = http_request(
            "GET",
            f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/outreach-jobs?outreach_request_id={request_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        jobs = json.loads(raw)
        if not jobs:
            raise RuntimeError(
                "no OutreachJob yet - Event Dispatcher/Step Runner haven't picked up the run request yet"
            )
        job = jobs[0]  # list_outreach_jobs orders by created_at desc
        if job.get("status") not in ("completed", "failed", "cancelled"):
            raise RuntimeError(f"OutreachJob {job.get('id')} still status={job.get('status')!r}")
        return job

    job = poll(attempt, attempts=WORKER_POLL_ATTEMPTS, delay=WORKER_POLL_DELAY_SECONDS)
    if job.get("status") != "completed":
        raise RuntimeError(f"unexpected terminal job status: {job}")
    return f"job {job.get('id')} status={job.get('status')} (queued -> polled to completion)"


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


# --- M5 checks: Outreach Delivery Engine ---------------------------------

# The exact string dispatch_service._fail_item logs when a SendingProfile
# has no usable ProviderConnection - see dispatch_service.py's docstring.
# Asserted verbatim (not just "status == failed") so this step actually
# proves the intended code path fired, not just any failure.
NO_CONNECTION_ERROR = "SendingProfile has no usable ProviderConnection - connect or reconnect it first."


def check_connectable_providers() -> str:
    token = _state.get("token")
    if not token:
        raise RuntimeError("skipped — no access token from the login step")

    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/delivery/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    providers = json.loads(raw)
    if not isinstance(providers, list):
        raise RuntimeError(f"expected a list, got: {providers}")
    return f"{len(providers)} connectable provider(s) configured in this environment"


def check_create_sending_profile() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    if not token or not profile_id:
        raise RuntimeError("skipped — no token/company_profile_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/sending-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "provider_key": "gmail",
            "label": "Smoke Test Sending Profile",
            "sender_name": "Smoke Test Sender",
            "sender_email": "smoke-test-sender@example.com",
            # No provider_connection_id - deliberately unconnected, so
            # dispatch_service's deterministic no-credential failure path
            # (see NO_CONNECTION_ERROR above) is what steps 41/44 exercise.
            # Window widened to cover the entire UTC day so
            # campaign_service._schedule_group's effective_start always
            # falls inside [window_start, window_end) regardless of what
            # time this smoke test happens to run.
            "sending_window_start": "00:00:00",
            "sending_window_end": "23:59:59",
            "sending_timezone": "UTC",
            "min_gap_seconds": 1,
            "max_gap_seconds": 2,
        },
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    sending_profile_id = payload.get("id")
    if not sending_profile_id:
        raise RuntimeError(f"no id in response: {payload}")
    if payload.get("provider_connection_id") is not None:
        raise RuntimeError(f"expected provider_connection_id=None, got: {payload.get('provider_connection_id')}")
    _state["sending_profile_id"] = sending_profile_id
    return f"created sending profile id={sending_profile_id}"


def check_update_sending_profile() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    sending_profile_id = _state.get("sending_profile_id")
    if not all([token, profile_id, sending_profile_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/sending_profile_id from earlier steps")

    status, raw = http_request(
        "PUT",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/sending-profiles/{sending_profile_id}",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"label": "Smoke Test Sending Profile (updated)"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("label") != "Smoke Test Sending Profile (updated)":
        raise RuntimeError(f"label was not updated: {payload}")
    return f"sending profile {sending_profile_id} label updated"


def _list_available_draft_ids(token: str, profile_id: str) -> set:
    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/available-drafts",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    return {d["id"] for d in json.loads(raw)}


def check_available_drafts_includes_m4_draft() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    draft_id = _state.get("outreach_draft_id")
    if not all([token, profile_id, draft_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/outreach_draft_id from earlier steps")

    available = _list_available_draft_ids(token, profile_id)
    if draft_id not in available:
        raise RuntimeError(f"expected draft {draft_id} in available-drafts, got ids: {available}")
    return f"draft {draft_id} available for a new campaign"


def check_create_delivery_campaign() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    sending_profile_id = _state.get("sending_profile_id")
    draft_id = _state.get("outreach_draft_id")
    if not all([token, profile_id, sending_profile_id, draft_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/sending_profile_id/outreach_draft_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "sending_profile_id": sending_profile_id,
            "name": "Smoke Test Campaign",
            "outreach_draft_ids": [draft_id],
        },
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    campaign_id = payload.get("id")
    if not campaign_id:
        raise RuntimeError(f"no id in response: {payload}")
    if payload.get("status") != "draft":
        raise RuntimeError(f"expected status='draft' on creation, got: {payload.get('status')}")
    _state["delivery_campaign_id"] = campaign_id
    return f"created delivery campaign id={campaign_id}"


def _get_single_queue_item(token: str, profile_id: str, campaign_id: str) -> dict:
    status, raw = http_request(
        "GET",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/queue-items",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    items = json.loads(raw)
    if len(items) != 1:
        raise RuntimeError(f"expected exactly 1 queue item, got {len(items)}: {items}")
    return items[0]


def check_schedule_delivery_campaign() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    campaign_id = _state.get("delivery_campaign_id")
    if not all([token, profile_id, campaign_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/delivery_campaign_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") != "active":
        raise RuntimeError(f"expected status='active' after scheduling, got: {payload.get('status')}")

    item = _get_single_queue_item(token, profile_id, campaign_id)
    if item.get("status") != "scheduled":
        raise RuntimeError(f"expected queue item status='scheduled', got: {item.get('status')}")
    if not item.get("scheduled_send_at"):
        raise RuntimeError(f"expected scheduled_send_at to be set, got: {item}")
    _state["queue_item_id"] = item["id"]
    return f"campaign active, queue item {item['id']} scheduled_send_at={item.get('scheduled_send_at')}"


def check_worker_dispatches_to_failed() -> str:
    """The centerpiece of the M5 smoke test extension - see this file's
    module docstring. Waits for the independent `worker` container (its
    own process, own poll loop, own clock - not something this script
    triggers) to claim the item via SELECT...FOR UPDATE SKIP LOCKED and
    call dispatch_service.dispatch() on it. With no ProviderConnection
    attached, that call is deterministic: it always ends in FAILED with
    NO_CONNECTION_ERROR. No mocking, no fixtures - this is the real
    worker process, the real dispatch_service, the real DB."""
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    campaign_id = _state.get("delivery_campaign_id")
    item_id = _state.get("queue_item_id")
    if not all([token, profile_id, campaign_id, item_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/delivery_campaign_id/queue_item_id from earlier steps")

    def attempt():
        status, raw = http_request(
            "GET",
            f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        payload = json.loads(raw)
        if payload.get("status") not in ("failed",):
            raise RuntimeError(f"still status={payload.get('status')!r} - worker hasn't dispatched it yet")
        return payload

    payload = poll(attempt, attempts=WORKER_POLL_ATTEMPTS, delay=WORKER_POLL_DELAY_SECONDS)
    if payload.get("last_error") != NO_CONNECTION_ERROR:
        raise RuntimeError(f"expected last_error={NO_CONNECTION_ERROR!r}, got: {payload.get('last_error')!r}")
    if payload.get("attempt_count") != 1:
        raise RuntimeError(f"expected attempt_count=1 on first dispatch, got: {payload.get('attempt_count')}")
    _state["failed_attempt_count"] = payload.get("attempt_count")
    return f"worker dispatched queue item {item_id} to FAILED with the expected no-connection error"


def check_available_drafts_includes_draft_again() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    draft_id = _state.get("outreach_draft_id")
    if not all([token, profile_id, draft_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/outreach_draft_id from earlier steps")

    available = _list_available_draft_ids(token, profile_id)
    if draft_id not in available:
        raise RuntimeError(f"expected FAILED to release draft {draft_id} back to available-drafts, got ids: {available}")
    return f"draft {draft_id} released back to available-drafts after FAILED"


def check_retry_now() -> str:
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    campaign_id = _state.get("delivery_campaign_id")
    item_id = _state.get("queue_item_id")
    if not all([token, profile_id, campaign_id, item_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/delivery_campaign_id/queue_item_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}/retry",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") != "scheduled":
        raise RuntimeError(f"expected status='scheduled' after retry, got: {payload.get('status')}")
    return f"queue item {item_id} rescheduled via retry-now"


def check_worker_dispatches_retry_to_failed() -> str:
    """Same deterministic outcome as check_worker_dispatches_to_failed,
    but proves a SECOND, independent worker tick against an item that
    manual Retry Now (not the scheduler) put back into SCHEDULED -
    exercising queue_service.retry_now's integration with the worker, not
    just its own unit-tested logic."""
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    campaign_id = _state.get("delivery_campaign_id")
    item_id = _state.get("queue_item_id")
    if not all([token, profile_id, campaign_id, item_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/delivery_campaign_id/queue_item_id from earlier steps")

    def attempt():
        status, raw = http_request(
            "GET",
            f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if status != 200:
            raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
        payload = json.loads(raw)
        if payload.get("status") not in ("failed",):
            raise RuntimeError(f"still status={payload.get('status')!r} - worker hasn't re-dispatched it yet")
        return payload

    payload = poll(attempt, attempts=WORKER_POLL_ATTEMPTS, delay=WORKER_POLL_DELAY_SECONDS)
    if payload.get("attempt_count") != 2:
        raise RuntimeError(f"expected attempt_count=2 after a second dispatch, got: {payload.get('attempt_count')}")
    return f"worker re-dispatched queue item {item_id} to FAILED again, attempt_count=2"


def check_campaign_pause_resume_cancel_lifecycle() -> str:
    """Deliberately never scheduled - the queue item stays QUEUED for the
    whole test, so this has zero race window against the independent
    worker process (which only ever claims SCHEDULED items whose
    scheduled_send_at has passed). Reuses the draft released in the
    previous FAILED step."""
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    sending_profile_id = _state.get("sending_profile_id")
    draft_id = _state.get("outreach_draft_id")
    if not all([token, profile_id, sending_profile_id, draft_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/sending_profile_id/outreach_draft_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "sending_profile_id": sending_profile_id,
            "name": "Smoke Test Campaign 2 (pause/resume/cancel)",
            "outreach_draft_ids": [draft_id],
        },
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status} creating campaign 2: {raw[:200]!r}")
    campaign_id = json.loads(raw)["id"]

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/pause",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 200 or json.loads(raw).get("status") != "paused":
        raise RuntimeError(f"pause failed: status={status} body={raw[:200]!r}")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/resume",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 200 or json.loads(raw).get("status") != "active":
        raise RuntimeError(f"resume failed: status={status} body={raw[:200]!r}")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json_body={},
    )
    if status != 200 or json.loads(raw).get("status") != "cancelled":
        raise RuntimeError(f"cancel failed: status={status} body={raw[:200]!r}")

    item = _get_single_queue_item(token, profile_id, campaign_id)
    if item.get("status") != "cancelled":
        raise RuntimeError(f"expected the queue item to cascade-cancel with its campaign, got: {item.get('status')}")

    return f"campaign {campaign_id}: draft -> paused -> active -> cancelled, queue item cascade-cancelled"


def check_queue_item_direct_cancel() -> str:
    """Distinct from the previous step's campaign-level cascade cancel -
    this hits DeliveryQueueItemCancel/queue_service.cancel_queue_item
    directly, the single-item action a user takes from a campaign's queue
    table rather than cancelling the whole campaign."""
    token = _state.get("token")
    profile_id = _state.get("company_profile_id")
    sending_profile_id = _state.get("sending_profile_id")
    draft_id = _state.get("outreach_draft_id")
    if not all([token, profile_id, sending_profile_id, draft_id]):
        raise RuntimeError("skipped — missing token/company_profile_id/sending_profile_id/outreach_draft_id from earlier steps")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "sending_profile_id": sending_profile_id,
            "name": "Smoke Test Campaign 3 (direct item cancel)",
            "outreach_draft_ids": [draft_id],
        },
    )
    if status != 201:
        raise RuntimeError(f"unexpected status {status} creating campaign 3: {raw[:200]!r}")
    campaign_id = json.loads(raw)["id"]
    item = _get_single_queue_item(token, profile_id, campaign_id)
    if item.get("status") != "queued":
        raise RuntimeError(f"expected a fresh, unscheduled item to be 'queued', got: {item.get('status')}")

    status, raw = http_request(
        "POST",
        f"{BACKEND_URL}/api/v1/company-profiles/{profile_id}/delivery-campaigns/{campaign_id}/queue-items/{item['id']}/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json_body={"reason": "smoke test direct cancel"},
    )
    if status != 200:
        raise RuntimeError(f"unexpected status {status}: {raw[:200]!r}")
    payload = json.loads(raw)
    if payload.get("status") != "cancelled":
        raise RuntimeError(f"expected status='cancelled', got: {payload.get('status')}")
    if payload.get("cancelled_reason") != "smoke test direct cancel":
        raise RuntimeError(f"expected cancelled_reason to round-trip, got: {payload.get('cancelled_reason')}")
    return f"queue item {item['id']} directly cancelled"


def main() -> int:
    print("Sales Agent — M0 + M1.1 + M1 + M2 + M3 + M4 + M5 smoke test")
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
    all_passed &= step("Connectable providers reachable", check_connectable_providers)
    all_passed &= step("SendingProfile creation succeeds", check_create_sending_profile)
    all_passed &= step("SendingProfile update succeeds", check_update_sending_profile)
    all_passed &= step("Available drafts include the M4 draft", check_available_drafts_includes_m4_draft)
    all_passed &= step("DeliveryCampaign creation succeeds", check_create_delivery_campaign)
    all_passed &= step("DeliveryCampaign schedule succeeds", check_schedule_delivery_campaign)
    all_passed &= step("Worker dispatches to a deterministic FAILED", check_worker_dispatches_to_failed)
    all_passed &= step("Available drafts include the draft again", check_available_drafts_includes_draft_again)
    all_passed &= step("Queue item Retry Now succeeds", check_retry_now)
    all_passed &= step("Worker dispatches the retry to FAILED too", check_worker_dispatches_retry_to_failed)
    all_passed &= step("Campaign pause/resume/cancel lifecycle", check_campaign_pause_resume_cancel_lifecycle)
    all_passed &= step("Queue item Cancel succeeds", check_queue_item_direct_cancel)

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
