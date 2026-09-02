# Optional CloudBase integration

This adapter is optional. The workbench defaults to `local`, has no login,
network request, scheduled task, or model call. Copy the example config outside
the repository and set `cloudbase.enabled` only after completing your own
CloudBase authentication and RLS review. Do not put API keys in this folder.

Apply the migrations in ascending order to a fresh self-hosted database. Every
table is owner-only under RLS; a service credential, if needed by a local Agent,
must stay in an OS-protected private adapter directory.

The additive migrations include training-session correction snapshots,
nutrition subjective check-ins, and an owner-only `local_archive` queue. The
archive RPC only creates a request; exporting database facts to disk remains a
private-adapter responsibility because the public repository has no endpoint or
credential.

The local Agent is deliberately not installed by default. When installed it is
manual-only, has zero recurring triggers, and performs one explicit queue check
only. The web task helper also performs exactly one known-job read per click.
On Windows an explicitly installed custom protocol can start one hidden `-Once`
run; it accepts no local path from the web page and creates no scheduled task.

Run the safety check without credentials or a database connection:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\local-agent\Test-LocalAgentSafety.ps1
```

The complete user flow and Windows protocol boundary are documented in
[`docs/CloudBase-Agent-Runbook.md`](../../docs/CloudBase-Agent-Runbook.md).
