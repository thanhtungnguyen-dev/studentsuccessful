"""Bounded HTTP smoke check for an already healthy Compose or native stack."""

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(url, expected=200, origin=None):
    headers = {}
    data = None
    if origin is not None:
        headers = {"Origin": origin, "Content-Type": "application/json"}
        data = json.dumps({"email": "r4-smoke-missing@example.com", "password": "R4-smoke-password-123!"}).encode()
    try:
        response = urlopen(Request(url, data=data, headers=headers), timeout=10)
    except HTTPError as error:
        response = error
    with response:
        body = response.read().decode()
        assert response.status == expected, f"{url}: expected {expected}, got {response.status}: {body}"
    print(f"PASS {url} = {expected}" + (f" (Origin: {origin})" if origin else ""))
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", default="http://localhost:3000")
    parser.add_argument("--backend", default="http://localhost:8000")
    args = parser.parse_args()
    assert "StudentSuccessful" in request(args.frontend + "/")
    for base in (args.backend, args.frontend):
        assert json.loads(request(base + "/health/live"))["status"] == "ok"
        ready = json.loads(request(base + "/health/ready"))
        assert ready["status"] == "ready"
        assert ready["dependencies"] == {"database": True, "storage": True}
    # Existing-user creation and cookie/UI flows belong to R5. This request is read-only.
    login = args.frontend + "/api/v1/auth/login"
    request(login, 401, args.frontend)
    rejected = json.loads(request(login, 403, "https://foreign.example"))
    assert rejected["code"] == "AUTH_ORIGIN_REJECTED"


if __name__ == "__main__":
    main()
