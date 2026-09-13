# RUNBOOK — External/BYO MCP server

Procedure only — no narration, no environment-specific history. This file
stays generic on purpose so it doesn't go stale as it's reused across
instances.

**Before anything else**: `git pull` this repo, and diff your plan against
a known-working reference environment if one exists (another instance's
Application Registry + Auth Scope chain, field-by-field) rather than
relying on memory or this runbook alone.

---

## 1. System property

Confirm `glide.oauth.inbound.client.credential.grant_type.enabled` is
enabled on the target instance (System Properties, or search directly).
Without it, `client_credentials` fails with an error naming **PKCE** —
misleading; has nothing to do with PKCE. This is instance-level and does
not travel with any record — check it fresh on every new instance.

## 2. OAuth Application Registry

**System OAuth → Application Registry → New → "Create an OAuth API endpoint
for external clients"** (deprecated-UI label, still the right choice for
this pattern — Type ends up `OAuth Client`).

| Field | Value | Note |
|---|---|---|
| Type | OAuth Client | confirmed via `type` field on `oauth_entity` |
| **Client Type** (dropdown: None / Iframe Embedded / Integration as a User / Integration as a Service) | **`-- None --`** | A red herring on some releases — don't assume "Integration as a Service" means client_credentials. |
| **Inbound Grant Type** (a *different*, separate field, further down the form) | **Client Credentials** | This is the field that actually matters — easy to conflate with Client Type above since both live on the same form. |
| User | a real, valid ServiceNow user | The classic Application Registry form's User field has no restrictive filter — it's a plain reference to every `sys_user` record. A separate "New Inbound Integration Experience" wizard applies its own, more restrictive filter — if a user picker seems to show nobody, try the other form before assuming a user-record problem. |
| Access Token Lifespan | 1800 | reasonable default |
| Refresh Token Lifespan | 8640000 | reasonable default |
| Token Format | Opaque | for this pattern (client_credentials); native MCP Server Console builds use JWT instead — see `native/RUNBOOK.md` |
| Send Client Credentials As | In Request Body (Form URL-Encoded) | |
| Public Client / PKCE | both off | |
| Access | Public / "All application scopes" | tighten for anything beyond a sandbox build |

Save. Client ID is fine to note down; **never display or transcribe the
Client Secret anywhere durable** (chat, terminal history, screen recording).

## 3. Auth Scope chain — do not skip this

The registry alone authenticates the client; it does **not** by itself
authorize any API access. This step is easy to miss because nothing on the
main registry form indicates it's missing — the failure only shows up
later as a 403 on an actual API call.

From the **Auth Scopes related list at the bottom of the Application
Registry record**, click **New** — this walks through all three of the
following in one flow (don't build them as three disconnected manual
records unless the related-list flow isn't available):

1. **Authentication Scope** (`sys_auth_scope`) — a named scope.
2. **REST API Auth Scope** (`sys_api_access_scope`) — grants that scope
   access to the **Table API** (`api_path` = `now/table`), with
   `apply_all_resources`, `apply_all_methods`, `apply_all_versions` all
   true, `active` true.
3. **The mapping** (`oauth_entity_auth_scope_mapping`) linking the
   registry to the scope from step 1.

To verify programmatically instead of eyeballing the UI (via any read
access you have):
```
get_record(table="oauth_entity", sys_id="<registry sys_id>")
query_records(table="oauth_entity_auth_scope_mapping", sysparm_query="oauth_entity=<registry sys_id>")
query_records(table="sys_api_access_scope", sysparm_query="auth_scope=<scope sys_id>")
```

## 4. Verify the token mints — independent of any Python code

Before touching `server.py`, Keychain, or Claude Code at all, confirm the
registry + scope chain actually work with a raw request:

```bash
# Capture the secret without it ever appearing on screen or in shell history.
# zsh syntax (macOS default shell) — read -p means something different in
# zsh (reads from a coprocess) than in bash, so this uses zsh's own
# varname?prompt form instead:
read -s "SN_SECRET?Client Secret: "; echo
# bash equivalent, if you're in a bash shell instead:
#   read -s -p "Client Secret: " SN_SECRET; echo

curl -s -X POST "https://<instance-host>/oauth_token.do" \
  -d "grant_type=client_credentials" \
  -d "client_id=<your client id>" \
  --data-urlencode "client_secret=$SN_SECRET" \
  -H "Accept: application/json"

unset SN_SECRET
```

Expect a JSON body with `access_token`, `token_type`, `expires_in`. If this
fails, the problem is ServiceNow-side (property, registry, or scope chain)
— rule it out here before suspecting the Python server.

**Why `read -s` + a shell variable instead of typing the secret directly
into the `curl` command:** typing it inline puts the literal secret into
your shell history and onto the screen. Capturing it into a variable via
silent input keeps the secret out of both, and `--data-urlencode` handles
any special characters safely. Unset the variable afterward.

## 5. Role/ACL check

Confirm the identity behind the token (the `User` field from step 2) has
roles covering every table currently in `READ_TABLES`/`WRITE_TABLES` in
`server.py`. A token that mints fine can still 403/404 on a specific table
if the identity lacks role/ACL access — a separate failure mode from
everything above.

**If this instance needs different tables** than the minimal starting
point in `server.py`, edit the file now, with clear inline comments on
what was added and why — then **commit and push before moving on**, not
batched in with unrelated later changes. This is the whole point of
keeping the allowlist in source control: your team can review what any
given agent is permitted to touch, which only works if each change is
committed as it happens. Never commit a Client Secret or any value that
came out of Keychain — only table names and comments belong in git.

## 6. Keychain

```bash
cd external
./setup_keychain.sh
```
Stores instance host, client ID, client secret under one Keychain service
name. Never in env vars, disk, or shell history.

## 7. Register with Claude Code

```bash
python3 -m pip install -r requirements.txt
claude mcp add <server-name> "$(which python3)" "$(pwd)/server.py"
```
Restart Claude Code, then ask it to call `list_capabilities` to confirm
connectivity and see the configured allowlists.

## 8. Smoke test

One read (`query_records` or `get_record`) and one scoped write
(`create_record` or `update_record`) against a table already in the
allowlists. Confirm the write actually landed by checking the record in
the ServiceNow UI directly — don't just trust a "success" response.

## 9. Commit and push

Once the smoke test passes: commit any `server.py` changes made for this
instance (if not already pushed per step 5), and append anything new to
the Known Gotchas log below. Double-check `git diff` before committing for
anything that looks like a secret, even in a comment — nothing from
Keychain should ever reach this repo.

---

## Known Gotchas

- **`claude mcp add` registered against the wrong Python interpreter —
  fails as a bare `CONNECTION_CLOSED` with zero further detail.** On a Mac
  with more than one Python 3 installed (Apple's `/usr/bin/python3` +
  python.org's own installer are both common), each has entirely separate
  `site-packages`. Running `python3 -m pip install -r requirements.txt` in
  a terminal installs into whichever `python3` that terminal's PATH
  resolves to — which is **not necessarily** the interpreter you hardcode
  into `claude mcp add`. If they differ, the MCP server process crashes
  immediately on `import mcp` with no visible traceback — Claude Code just
  reports the connection closed. **Diagnostic:** run the server directly,
  `/path/to/that/python3 -c "import mcp"` — if that errors, you've found
  it. **Fix:** always register with the exact output of `which python3`
  from the same terminal session you ran `pip install` in, not a
  hardcoded guess; re-run `claude mcp add` (removing the old registration
  first) if it's already wrong, then restart Claude Code.
- **System property gates `client_credentials` silently**, with a
  misleading PKCE-named error if disabled.
- **Integration-user field not reliably populated with a dedicated
  service account on some releases** — root cause varies; a pragmatic
  fallback is an existing, real, valid named account. "Web service access
  only" on the associated user is a recurring, plausible-sounding theory
  for related failures, but has produced a confirmed *negative* result at
  least once — cheap to check, but don't treat it as the likely fix; go
  straight to the System Log instead of iterating on that checkbox
  repeatedly.
- **A specific error like `"...integration user is not configured for
  OAuth:<sys_id>"` can mean the registry's User field holds a sys_id with
  no matching record at all** — a dangling/broken reference, not a
  configuration gap. Confirm by opening `<instance>/sys_user.do?sys_id=<the
  sys_id from the error message>` directly. **Diagnostic worth reusing:**
  don't try to find a user by pasting its sys_id into the global "All"
  search bar — that frequently returns nothing even for real records,
  since global search indexes text fields, not raw sys_id values. Go
  straight to `<instance>/<table>.do?sys_id=<id>` instead. Fix: clear and
  properly reselect the User field, confirming it resolves to a real
  display name before saving.
- **Auth Scope chain is required and not obvious from the registry form**
  — a 403 with no other clue is the usual symptom of skipping it.
- **Client secret can be silently invalidated by re-migrating an update
  set that happens to contain the OAuth registry record** — regenerate
  and re-test after any such migration.
- **A "successful" Table API write can still silently fail to save a
  specific field** (seen on variable-name-style reference fields) — always
  spot-check the actual record after a write that matters, not just the
  API response.
- **Per-user role/ACL grants do not reliably travel via update set** even
  when it shows "Committed" — re-verify roles per environment after any
  migration, don't trust the update-set status alone.
- **A leftover placeholder character (`<`/`>`) when copying the curl
  command template into a real instance URL produces the exact same
  generic `{"error":"access_denied","error_description":"server_error"}`
  as a real auth failure** — indistinguishable without checking the URL
  itself first. Before chasing the System Log, re-read the literal command
  you just ran for template artifacts.
- **The OAuth identity's own "current update set" pointer is independent
  of whatever update set a human operator has active in their browser** —
  writes can silently land in a shared default bucket. Check/set this
  before any write that needs to travel with a specific change.

Append here every time a new environment surfaces something this runbook
didn't already cover.
