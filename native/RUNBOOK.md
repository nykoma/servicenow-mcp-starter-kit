# RUNBOOK — Native ServiceNow MCP server (`sn_mcp_server` / MCP Server Console)

Procedure only — no narration, no environment-specific history. This file
stays generic on purpose so it doesn't go stale as it's reused across
instances.

**Before anything else**: `git pull` this repo. Then verify your target
instance's actual patch level directly (`sys_properties`, `glide.war`) —
**don't infer it from a docs page's "current release" framing, and don't
assume parity with any other instance you've built this on before**,
even one on the same release family. Scripted REST API tool support
specifically requires Zurich Patch 9 / Australia Patch 2 or later — a
later feature wave than the plugin's initial launch.

---

## 1. Confirm the plugin and record model

1. **Plugins → All Available Applications** → search "Model Context
   Protocol Server" (app `sn_mcp_server`) → Install, if not already
   installed.
2. Verify: `sys_service.list` in the filter navigator → find `MCP-S` and
   `mcp-server` records → open `mcp-server` → confirm its Service
   Endpoints related list has an Active record with URL
   `mcps-prod-default` → then `curl https://<instance>.service-now.com/sncapps/mcp-server/health`
   and confirm `{"status":"healthy"}`. Anything else means the install
   didn't complete — fix that before continuing.
3. **Create a dedicated scoped app** to hold everything you build — via
   Studio/IDE, build and install so it shows platform-side, then select
   it in the application picker before creating anything else. Keep this
   separate from any shared/platform-seeded scope that pre-existing
   example servers/tools live in.

**Record model reference** (useful for understanding what the console UI
is doing underneath, not required reading to complete a build):

| Concept | Real table |
|---|---|
| MCP Server | `sn_mcp_server` |
| Tool Definition (Scripted REST-backed) | `sn_mcp_scripted_rest_tool_definition` (subclass of `sn_mcp_tool_definition`) |
| Tool parameters | `sn_mcp_scripted_rest_input` / `sn_mcp_tool_input` |
| Server↔Tool link | `sn_mcp_server_tool_definition_assoc` (surfaced as a plain multi-select on both Server and Tool forms) |

The field that actually links a Tool to its REST endpoint is
`tool_artifact_id`, a JSON string (`{sysId, httpMethod, route}`) — the
console's "REST API" picker just writes this for you.

## 2. OAuth setup (Machine Identity Console)

**This is Authorization Code Grant, not Client Credentials** — a real
user-consent flow, structurally different from the external/BYO pattern
in `../external/RUNBOOK.md`. Don't reuse that runbook's steps.

1. Go to **Machine Identity Console → Inbound Integrations**
   (`/now/machine-identity-console/inbound-integrations`) → **New
   integration** → Authorization Code grant.
2. Set **Redirect URLs** — this is a single field, **comma-separated**,
   not a related list. Add whichever client(s) you intend to connect —
   for claude.ai (web) as your connecting client:
   `https://claude.ai/api/mcp/auth_callback` (exact match, no trailing
   slash).
3. **Set Token Format to JWT explicitly** — this is not the default
   (Opaque is), and leaving it on Opaque is the single most common
   silent-failure mode reported: the connection succeeds, but the client
   sees zero tools with no clear error. This is under **Advanced
   options**.
4. **Scope**: there is no official narrow-scope pattern to copy from
   ServiceNow's own docs. The registry form itself recommends enabling
   "Allow access only to APIs in selected scope," but this can silently
   break tool discovery by blocking the token from reaching
   `/sncapps/mcp-server`. **Test empirically** — if discovery breaks
   after restricting scope, that's your diagnostic. Never ship a broad
   `useraccount`-style scope beyond a sandbox build.
5. Save the registry. Note the **Client ID** and **Client Secret** — the
   secret should never be typed into a chat/assistant session; handle it
   yourself.

## 3. Scripted REST API (the actual implementation)

Build under your dedicated scoped app (never Global). **Only GET, POST,
and PUT resources can be wrapped as an MCP Tool — DELETE, PATCH, and the
Table API itself cannot**, by platform design.

General guidance, confirmed across at least one real build:

- Use **`GlideRecordSecure`**, not plain `GlideRecord`, for both reads and
  writes — ServiceNow's own recommended pattern for Scripted REST APIs
  generally; plain `GlideRecord` bypasses row-level ACLs entirely.
- **Resolve reference fields by explicit lookup, not `setDisplayValue()`.**
  That method silently "best-matches" on ambiguous/duplicate display
  names with no error — the wrong failure mode for an API a model calls
  unsupervised. Query the target table directly, reject on zero or
  multiple matches.
- **Journal fields append via direct property/bracket assignment**
  (`gr.work_notes = "text"`), not `setValue()` — `setValue()` on a
  journal field is documented as unreliable.
- **Check `canWrite()` before writing, and check `.update()`'s return
  value** (with `getLastErrorMessage()` on failure) — don't assume
  success.
- **Verify every field name, choice-list value, and enforced-requirement
  claim against the real target instance, not a generic example or a
  prior build.** Custom/legacy instances routinely rename or repurpose
  standard fields (e.g. a standard-sounding field can turn out unused,
  while a custom `u_`-prefixed field is the one actually populated on
  real records) — check real data, not just the dictionary, before
  trusting a field name.

For a POST/PUT resource, **create the schema record before attaching it**:

1. On the Tool record (after Step 4) → **Request Schema related list →
   New** → set Name, API (your Scripted REST API), OpenAPI Version
   (3.0.1), and the Schema itself — a plain OpenAPI Schema Object
   (`type: object`, `properties`, each with `type`/`description`/
   `example`, and `enum` for any choice-coded field).
2. **Use `enum` constraints for choice-coded fields, not just prose
   descriptions of what the codes mean.** Prose alone doesn't stop a
   malformed call from sending an out-of-range value — an explicit `enum`
   does.
3. **GET resources need no schema** — path parameters are auto-exposed as
   Tool Inputs.
4. Skipping the schema on a POST/PUT tool doesn't error — it just leaves
   the tool with no body inputs at all, silently useless.

**"OpenAPI" here is the REST industry standard** (Swagger-descended,
Linux Foundation) — unrelated to "OpenAI" the company, despite the naming
collision.

## 4. MCP Tool records

1. MCP Server Console → **Tools → Create tool**.
2. **Category: REST API.** Point the "REST API" field at your Scripted
   REST resource (method + route).
3. **Write the Description as an actual prompt to the model, not a
   summary.** ServiceNow's own console UI states plainly: *"The
   description will be used by your MCP clients to determine when to
   call this tool."* Write yours the same way — explicit value mappings,
   worked examples, not a one-line blurb.
4. Add Tool Inputs — one row per parameter (name, type, description,
   mandatory, optional hardcoded `static_value` if you want to pin a
   generic endpoint to a specific use case).
5. If this is the POST/PUT tool, attach its Request Schema (Step 3).

## 5. MCP Server record

1. MCP Server Console → **Servers → Create server**.
2. Attach your Tool(s) via the Tools related list (each has its own
   **Enabled** toggle, independent of the Tool's own Active flag).
3. **A Tool's application scope must match its Server's application
   scope** — keep both in the same scoped app from Step 1.

## 6. Connect Claude

**If you're on a Claude Enterprise plan**, check this before anything
else: "Add custom connector" under Settings → Connectors may not appear
at all. "Allow custom connectors" defaults ON for Team plans, **OFF for
Enterprise** — an org Owner/Primary Owner must enable it centrally, and
orgs with HIPAA compliance mode enabled cannot enable it at all,
regardless of role. If getting that approved isn't fast, **a personal
(non-Enterprise) claude.ai account works around this entirely** — the
toggle doesn't exist for individual accounts, and the ServiceNow-side
OAuth handshake doesn't care which Claude account performs it.

**Steps (claude.ai web, Settings → Connectors → Add → Custom → Web):**

1. Enter the MCP Server's URL.
2. Authentication: **"Sign in now"**.
3. OAuth client: **"Use your own OAuth client"** — enter the Client ID
   and Secret from the registry built in Step 2. (The console may also
   show "Use Claude's published identity" (CIMD) or "Register
   automatically" (DCR) as "Detected" — that's informational, not a
   recommendation to switch; "Use your own OAuth client" matches a
   manually-built registry and is the safer choice on a first attempt.)
4. Transport: **Streamable HTTP** (default).
5. Add → complete the OAuth consent redirect.

**If instead you're using Claude Code CLI** (`claude mcp add --transport
http` + `claude mcp login`): **this is a confirmed, currently
unresolvable dead end for this specific product**, not a config mistake.
ServiceNow's OAuth metadata endpoint reports one issuer for the whole
instance, not scoped per MCP server; Claude Code CLI (v2.1.232+) enforces
RFC 8414 §3.3's requirement that the metadata issuer match the queried
resource URL exactly, and rejects the mismatch. No flag disables this
check on the Claude Code side, and no ServiceNow setting produces a
per-server issuer on the ServiceNow side. Use claude.ai web instead.

## 7. Test

A read call and a scoped write call, through the actual connected client,
against whatever your Tool(s) wrap. Confirm the result against the real
record in the ServiceNow UI, not just the client's reported success.

---

## A note on AI Control Tower visibility

If your instance has ServiceNow's AI Control Tower installed, worth
knowing before you decide which pattern to build: **a native `sn_mcp_server`
build is auto-discovered into AI Control Tower's asset inventory
(`alm_mcp_digital_asset` / `cmdb_ci_function_mcp`) with zero manual
registration step** — confirmed directly on a real instance, not inferred
from docs. The server appears there (in the "Unmanaged" view — discovered,
not yet governance-reviewed) essentially as soon as it's created.

**An external/BYO MCP server (the `external/` pattern in this repo) does
not appear in either table at all.** It authenticates like any other OAuth
REST client, with nothing marking the traffic as coming from an MCP
server — so it's architecturally invisible to this specific governance
mechanism, regardless of how much real traffic it generates.

If your organization is relying on AI Control Tower as an inventory of
"what AI agents/MCP servers touch our data," that inventory is only as
complete as the native builds — worth factoring into which pattern you
choose, and worth knowing if you're auditing what's actually visible
today.

## Known Gotchas

1. **"Cannot edit in read-only editor" on a Scripted REST Resource's
   `operation_script` field** — not a scope, elevation, or Studio issue
   on Zurich-family releases. Zurich introduced **"Scripting
   Governance"**: editing any scriptable field requires a distinct role,
   **`snc_required_script_writer_permission`** (via a "Conditional
   Script Writer" group) — **`admin` and `security_admin` do NOT include
   this by default.** Fix: add the role, then **fully log out and back
   in** — elevating mid-session is not enough.
2. **On Claude Enterprise plans, "Add custom connector" may not appear at
   all** — see Step 6. Fastest workaround: a personal (non-Enterprise)
   claude.ai account.
3. **Claude Code CLI cannot connect to a self-built native MCP server —
   confirmed dead end, not a config problem.** See Step 6.
4. **The real MCP Server Console supports Authorization Code Grant
   only** — don't reuse an external/BYO server's Client Credentials OAuth
   steps for this build.
5. **Token Format defaulting to Opaque instead of JWT** is the most
   common silent-failure mode — connection succeeds, tool list comes back
   empty, no clear error pointing at the cause.
6. **DELETE and PATCH resources cannot be wrapped as MCP Tools at all,
   nor can the Table API** — a platform limitation, not a config gap.
7. **An overly-restrictive custom OAuth scope can silently break tool
   discovery** by blocking the token from reaching
   `/sncapps/mcp-server` — creates real tension with the registry form's
   own "recommended" scope restriction. Test empirically.
8. **A Tool's application scope must match its Server's application
   scope.**
9. **Stray or duplicate OAuth inbound-integration records** are a
   commonly reported cause of "authenticated but empty tools" — check for
   multiple client IDs/registries with overlapping scope before assuming
   a code/config bug.
10. **Don't trust an empty Table API query result against any
    `sn_mcp_*` table as proof nothing exists** — silent ACL-filtering can
    differ between a service-account query and an interactive admin
    session. Cross-check the console UI directly before concluding a
    table is empty.
11. **`sn_mcp_tool_definition` is not empty out of the box on most
    instances** — it typically holds platform-seeded example rows.
    Filter for your own work, don't assume a blank slate.
12. **This instance's actual patch level matters and isn't always what
    you'd assume** — verify directly (`sys_properties`, `glide.war`)
    rather than assuming parity with another instance you've built this
    on before, even one on the same release family.
