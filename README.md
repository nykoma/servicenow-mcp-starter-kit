# ServiceNow MCP Starter Kit

A clean, reusable starting point for connecting Claude (or any MCP client)
to a ServiceNow instance. Two independent patterns are covered — pick the
one that fits your situation, or read both:

- **`external/`** — a small external MCP server you run yourself (stdio
  transport, OAuth 2.0 Client Credentials, explicit table allowlists in
  code). Full control, but you own running and securing a process.
- **`native/`** — using ServiceNow's own built-in `sn_mcp_server` plugin
  ("MCP Server Console") to expose a Scripted REST API as an MCP tool,
  with no external process at all. Less code, but you're working within
  the platform's current constraints (GET/POST/PUT only, Authorization
  Code Grant OAuth, JWT tokens).

This repo intentionally contains **only the reusable pattern** — generic
code, a clean step-by-step procedure, and gotchas that are genuinely
instance-independent. It does not assume any specific instance's field
names, patch level, or environment quirks — verify those against your own
target instance as you go (see the note at the bottom of this README).

Maintained by [Delante Bess](https://github.com/delante-nykoma). Issues
and PRs welcome.

## Prerequisites — GitHub access

If you're new to git/GitHub:

1. **Git installed locally** (macOS: `git --version` will prompt an
   install via Xcode Command Line Tools if missing).
2. **A GitHub account.**
3. **An authentication method configured** — an SSH key added to your
   GitHub account, or a personal access token (PAT) for HTTPS. Without
   one of these, `git clone`/`git push` will fail with an auth error.
4. **Clone this repo**:
   `git clone https://github.com/delante-nykoma/servicenow-mcp-starter-kit.git`
5. **`git pull`** before starting any build, to make sure you're working
   from the current version.

## Which pattern should I use?

- Want full code-level control over exactly what your agent can read/write,
  and don't mind running a small local process? → `external/`
- Want no external process at all, and are comfortable working within
  ServiceNow's current native MCP feature set? → `native/`
- Not sure? Start with `external/` — it's the simpler on-ramp, and the
  concepts (OAuth, table allowlists, least privilege) carry over either way.

## A note on instance-specific verification

**Every ServiceNow instance is different** — patch level, custom fields,
choice-list values, and enforcement rules can all vary, especially on a
legacy or heavily-customized instance. Both RUNBOOKs in this repo are
written generically on purpose. Before relying on any specific field name,
choice value, or "this is required" claim in either RUNBOOK, verify it
against your actual target instance — don't assume it transfers unchanged
from wherever it was last built.
