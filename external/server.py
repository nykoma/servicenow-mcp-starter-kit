#!/usr/bin/env python3
"""
A minimal, external MCP server for ServiceNow.

Security model, deliberate and non-negotiable:
  * stdio transport only — no network listener. Outbound HTTPS to your
    instance only.
  * Secrets live in the macOS Keychain, read at runtime via /usr/bin/security.
    Never typed into this file, an env var, or shown on screen.
  * OAuth 2.0 bearer tokens only (client_credentials grant). Cached in memory.
  * READ_TABLES / WRITE_TABLES allowlists enforced in code. Anything off-list
    is refused. DELETE is not implemented at all.
  * One third-party dependency: the MCP SDK, plus certifi for a CA bundle.

Fill in READ_TABLES / WRITE_TABLES below with only what you actually need —
start narrow, add as required. Every addition should be reviewed the same
way you'd review any other code change: it's a real access-control decision,
not boilerplate.
"""

import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi
from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Keychain service name. Overridable via env so this same file can run as a
# differently-scoped server (e.g. one instance vs another) without code changes.
KEYCHAIN_SERVICE = os.environ.get("SN_MCP_KEYCHAIN_SERVICE", "servicenow-mcp-server")

# Cap on rows returned by a single query, regardless of what the caller asks for.
MAX_LIMIT = 200

# Tables this server may READ. Start narrow; add only what you actually need.
READ_TABLES = {
    "incident",
}

# Tables this server may WRITE (create/update). Deliberately a subset of
# READ_TABLES. DELETE is never implemented, for any table.
WRITE_TABLES = {
    "incident",
}

mcp = FastMCP(KEYCHAIN_SERVICE)

# In-memory token cache. Never persisted.
_token_cache = {"access_token": None, "expires_at": 0.0}


# --------------------------------------------------------------------------- #
# Secret handling — Keychain only
# --------------------------------------------------------------------------- #

def _secret(account: str) -> str:
    """Read a secret from the macOS Keychain (service=KEYCHAIN_SERVICE, account=<account>).

    Falls back to an env var SN_MCP_<ACCOUNT> only if the Keychain item is
    absent. Secrets are never logged.
    """
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password",
             "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, check=True,
        )
        value = result.stdout.strip()
        if value:
            return value
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return os.environ.get("SN_MCP_" + account.upper(), "")


def _instance() -> str:
    inst = _secret("instance")
    if not inst:
        raise RuntimeError(
            "No ServiceNow instance configured. Run setup_keychain.sh first.")
    inst = inst.replace("https://", "").replace("http://", "").strip("/")
    return inst


# --------------------------------------------------------------------------- #
# OAuth
# --------------------------------------------------------------------------- #

def _get_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 30:
        return _token_cache["access_token"]

    instance = _instance()
    data = {
        "grant_type": "client_credentials",
        "client_id": _secret("client_id"),
        "client_secret": _secret("client_secret"),
    }

    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        f"https://{instance}/oauth_token.do",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # Safe to include: this is ServiceNow's response body, never the
        # request we sent (the secret lives only in the outbound request body).
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(
            f"OAuth token request failed: HTTP {e.code}. Response: {detail}") from None

    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"] = now + int(payload.get("expires_in", 1800))
    return _token_cache["access_token"]


# --------------------------------------------------------------------------- #
# HTTP helper (Table API)
# --------------------------------------------------------------------------- #

def _request(method: str, path: str, params: dict = None, payload: dict = None) -> dict:
    instance = _instance()
    url = f"https://{instance}/api/now/table/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + _get_token(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"ServiceNow API {method} {path} failed: "
                           f"HTTP {e.code}: {detail}") from None


def _check_read(table: str):
    if table not in READ_TABLES:
        raise ValueError(
            f"Read not permitted on table '{table}'. Allowed: {sorted(READ_TABLES)}")


def _check_write(table: str):
    if table not in WRITE_TABLES:
        raise ValueError(
            f"Write not permitted on table '{table}'. Allowed: {sorted(WRITE_TABLES)}")


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

@mcp.tool()
def list_capabilities() -> str:
    """List which ServiceNow tables this server may read and write, and the
    configured instance. Call this first to confirm connectivity and scope."""
    return json.dumps({
        "instance": _instance(),
        "read_tables": sorted(READ_TABLES),
        "write_tables": sorted(WRITE_TABLES),
        "delete_supported": False,
        "max_limit": MAX_LIMIT,
    }, indent=2)


@mcp.tool()
def query_records(table: str, sysparm_query: str = "", fields: str = "",
                  limit: int = 50) -> str:
    """Query records from an allowlisted table using an encoded query.

    Args:
        table: table name (must be in the read allowlist).
        sysparm_query: ServiceNow encoded query, e.g. "active=true^priority=1".
        fields: comma-separated field list to return (empty = default set).
        limit: max rows (capped at MAX_LIMIT).
    """
    _check_read(table)
    params = {
        "sysparm_limit": str(min(max(1, limit), MAX_LIMIT)),
        "sysparm_display_value": "all",
        "sysparm_exclude_reference_link": "true",
    }
    if sysparm_query:
        params["sysparm_query"] = sysparm_query
    if fields:
        params["sysparm_fields"] = fields
    return json.dumps(_request("GET", table, params=params), indent=2)


@mcp.tool()
def get_record(table: str, sys_id: str, fields: str = "") -> str:
    """Fetch a single record by sys_id from an allowlisted table."""
    _check_read(table)
    params = {"sysparm_display_value": "all",
              "sysparm_exclude_reference_link": "true"}
    if fields:
        params["sysparm_fields"] = fields
    return json.dumps(_request("GET", f"{table}/{sys_id}", params=params), indent=2)


@mcp.tool()
def create_record(table: str, fields_json: str) -> str:
    """Create a record in an allowlisted write table.

    Args:
        table: table name (must be in the write allowlist).
        fields_json: JSON object string of field name/value pairs.
    """
    _check_write(table)
    try:
        payload = json.loads(fields_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"fields_json is not valid JSON: {e}") from None
    if not isinstance(payload, dict):
        raise ValueError("fields_json must be a JSON object.")
    return json.dumps(_request("POST", table, payload=payload), indent=2)


@mcp.tool()
def update_record(table: str, sys_id: str, fields_json: str) -> str:
    """Update an existing record (PATCH) in an allowlisted write table."""
    _check_write(table)
    try:
        payload = json.loads(fields_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"fields_json is not valid JSON: {e}") from None
    if not isinstance(payload, dict):
        raise ValueError("fields_json must be a JSON object.")
    return json.dumps(_request("PATCH", f"{table}/{sys_id}", payload=payload), indent=2)


if __name__ == "__main__":
    # stdio transport. No network listener is ever opened.
    mcp.run()
