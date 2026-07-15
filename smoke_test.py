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
TOTAL_STEPS = 12


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


def main() -> int:
    print("Sales Agent — M0 + M1.1 smoke test")
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
