# Two Ways In: What Actually Happens When You Wire Claude to ServiceNow

*Delante Lee Bess — Nykoma Consulting*

Will Coffey published a piece a few weeks ago titled "ClaudeNow: The Wiring Diagram", arguing that everything Salesforce just packaged as Claudeforce (skills, MCP, permission inheritance) ServiceNow shipped a year ago as separate, vendor-supported parts, and that there's nothing to wait for if you're already on the platform. I totally agree with the thesis. I want to add the part his article doesn't cover, because it's the part most teams actually get stuck on: **which of the two ways you wire Claude into ServiceNow you pick determines what you can see and govern afterward, and the two paths are not interchangeable.**

This isn't theoretical for us. Over the past few weeks we've built both patterns end to end against real ServiceNow instances, hit the actual failure modes (not the happy path), and then went looking in AI Control Tower to see which pattern the platform actually knows about. The answer surprised us enough that it's worth writing up.

## The two patterns

**External (bring-your-own or BYO):** a small process you run yourself, i.e., stdio transport, OAuth 2.0 Client Credentials grant, opaque tokens, an explicit table allowlist in code. You own the process, you own the security boundary, and every table it can touch is a line you wrote and can review in a pull request.

**Native:** ServiceNow's own `sn_mcp_server` plugin, the MCP Server Console Coffey's Step 6 describes. Tools are Scripted REST APIs, subflows, or Knowledge Graph queries, registered against a server, no external process at all. Authorization Code Grant, JWT tokens, and, critically, every call executes as the authenticated end user, inheriting exactly the roles and ACLs they already have.

Coffey's article treats the native path (his Lane 2) as *the* Claudeforce-equivalent pattern, and functionally it is, permission inheritance, no per-user config, governed tools. What it doesn't mention is that the external pattern isn't a lesser version of that; it's a genuinely different trust model, and the platform treats it differently in ways that matter once you're running more than one developer against the same instance.

## The gotcha nobody's blog post mentions

Coffey's Step 7, when you register Claude as an OAuth client, set Token Format to JWT, "leave it on Opaque and Claude connects but lists zero tools" is real and we hit an even sharper version of it. Claude Code CLI (the terminal tool, not claude.ai) cannot connect to a native ServiceNow MCP server *at all*, for a reason that has nothing to do with configuration: ServiceNow's OAuth issuer is scoped to the whole instance, not per-server, which violates the issuer-matching requirement in RFC 8414 §3.3 (and the newer mix-up-attack protections in RFC 9207). This isn't a bug you fix with the right toggle, this may be an architectural mismatch between how ServiceNow issues OAuth tokens and what the MCP spec now requires of the authorization server. claude.ai's connector UI works around it; the CLI, as of this writing, does not. If your team's plan is "everyone builds MCP servers from their terminal," know that up front for the native path, it's a claude.ai (or Claude Desktop) connection, not a CLI one.

We also hit a Zurich-release wrinkle worth flagging for anyone still on a pre-Zurich mental model of ServiceNow security: **Scripting Governance**. Editing any scriptable field — the operation script on a Scripted REST API included, now requires a dedicated role (`snc_required_script_writer_permission`), separate from `admin` or `security_admin`. 

## What Control Tower actually sees

This is the finding I personally wanted to check myself rather than assume. AI Control Tower ships two inventory tables relevant here: `alm_mcp_digital_asset` ("MCP Digital Asset") and `cmdb_ci_function_mcp` ("MCP Function"). I queried both directly against a client's instance rather than trusting documentation or a plausible guess.

**Native MCP servers auto-discover into Control Tower.** Stand one up via the MCP Server Console and it shows up as a governed asset. It is visible, ownable, auditable, exactly as Coffey describes for AI Gateway. Good stuff!

**External MCP servers do not appear anywhere in Control Tower.** Confirmed by direct query, not by absence of evidence. A BYO server can hold a live, authenticated connection to production data, and from the platform's own governance surface, it is invisible. Not "under-governed", it is unfortunately not inventoried.

That's the piece I'd add to the wiring diagram. Coffey's governance section (AI Gateway, catalog intake, per-tool observability) is correct and important, but it's scoped to what ServiceNow's own MCP server produces. If your team or, more likely, a vendor working with your team who found a tutorial online, stands up an external MCP server against your instance, Control Tower will not tell you it exists. The governance gap isn't a missing feature; it's a structural blind spot in where the visibility tooling looks.

## What this means if you're running a team, not a demo

Once you have more than one developer building against shared instances, this stops being an architecture preference and becomes a governance decision:

- **If you standardize on native**, you get automatic inventory and per-user permission inheritance for free, at the cost of the CLI limitation above and whatever the MCP Server Console's current tool types (Scripted REST, subflow, Knowledge Graph) will let you build.
- **If you allow external servers**, you get full code-level control over exactly what's readable and writable. It is also reviewable in a pull request, versioned, diffable, but you're accepting that Control Tower can't see it, so *your own code review and an explicit table allowlist become the entire governance boundary*. No platform safety net...yet
- **The honest middle answer for a team**, which is what I told a senior developer who asked me almost this exact question: the tool allowlist in the server's source is your first line of defense (small, reviewable, PR'd before merge), and GitHub is the branch review. Who approved something is your second, because AI Control Tower's asset inventory literally cannot see this pattern to help you.

## Where I land

Coffey's right that there's nothing to wait for on ServiceNow. The parts are shipped, documented, and usable today. But "wire it up" undersells how much the *choice* between the two wiring paths matters once governance, not just capability, is the question. Native gets you Claudeforce's permission-inheritance story out of the box. External gets you precision and code-level review, at the cost of stepping outside the platform's own visibility tooling entirely. Know which trade you're making before your team scales past one developer and one instance.

*Delante Lee Bess is the founder of Nykoma Consulting, where he works on ServiceNow architecture and AI/MCP integrations. He's currently teaching ServiceNow developers to build both patterns hands-on.*
