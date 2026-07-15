#!/usr/bin/env python3
"""
Smoke test for Sales Agent — mandatory gate before starting any milestone.

Run this against an already-running `docker compose up --build` stack. It
does NOT start or stop containers itself; it only calls the running
services over HTTP, the same way a real client would, and reports
PASS/FAIL for each of the six checks the project's acceptance criteria
require:

    1. Backend starts       (GET /api/v1/health)
    2. Frontend starts      (GET http://localhost:5173)
    3. /docs responds       (GET /docs)
    4. Login succeeds       (POST /api/v1/auth/login with .env credentials)
    5. Company creation     (POST /api/v1/companies)
    6. Contact creation     (POST /api/v1/contacts)

Deliberately stdlib-only (urllib, not requests) so it runs on a bare
`python3` with nothing to install, on any machine that has Python.

Usage:
    python3 smoke_test.py
    make smoke-test

Exit code: 0 if all six checks pass, 1 if any fail.
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
    label = f"[{len(_results) + 1}/6] {name}"
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


def main() -> int:
    print("Sales Agent — M0 smoke test")
    print(f"backend={BACKEND_URL}  frontend={FRONTEND_URL}")
    print("(assumes `docker compose up --build` is already running)\n")

    all_passed = True
    all_passed &= step("Backend starts (/api/v1/health)", check_backend_health)
    all_passed &= step("Frontend starts", check_frontend)
    all_passed &= step("/docs responds", check_docs)
    all_passed &= step("Login succeeds", check_login)
    all_passed &= step("Company creation succeeds", check_create_company)
    all_passed &= step("Contact creation succeeds", check_create_contact)

    print("\n--- Summary ---")
    for name, passed, detail in _results:
        print(f"{'PASS' if passed else 'FAIL':4}  {name}")

    print()
    if all_passed:
        print("SMOKE TEST: PASS — all 6 checks succeeded.")
    else:
        print("SMOKE TEST: FAIL — see the failing step(s) above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
