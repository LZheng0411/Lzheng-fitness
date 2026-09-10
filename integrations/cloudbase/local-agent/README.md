# Local Agent: explicit once-only boundary

`Run-NutritionLocalAgent.ps1 -Once` checks an explicitly supplied exported
queue file one time. With no file it exits successfully without a model call.
The public repository contains no credentials, CloudBase endpoint, or model
adapter. A private adapter must claim a job idempotently before invoking a
model and write only a candidate result for user confirmation.

`-Watch` is diagnostic-only: it is capped at 10 minutes and stops after three
empty checks or three failures. It is never installed, launched on login, or
called by a web page.

For an explicit browser-to-local handoff on Windows, first create a private
config outside this repository with `queue_file` and `adapter_command`, then
run `Install-NutritionLocalAgent.ps1 -ConfigPath <private-config.json>` once.
The registered `lzheng-fitness-agent://run` action starts one hidden `-Once`
run. It has no timer, login trigger, scheduled task, or path supplied by the
web page. `Get-NutritionLocalAgentStatus.ps1` reports whether the private
config and runner still exist.


## Optional built-in Codex adapter

`CodexNutritionAdapter.ps1` can be used as the private config's `adapter_command`. It requires Python and the user's already installed/logged-in Codex CLI. It makes no API-key purchase and starts only when the explicit queue runner receives a job. Configure a model through `FITNESS_NUTRITION_MODEL` if desired; otherwise use the user's CLI default. No automatic fallback to a more expensive model.

For offline use, export a selected meal request from the workbench, then run `python CodexNutritionAdapter.py <request.json> <candidate.json>` and import that candidate into the same meal. Text-only requests work; photos are embedded privately in the request. Meal ID and revision bind the result to its source. Confirmation is always a separate user operation.

The queue runner supports `-JobId` and the URI supports only an optional UUID `?job=` selector. It never accepts a command or file path from a web URI. Runs have an eight-minute outer timeout and terminate the child process tree on Windows. `Get-NutritionUriSupport.ps1` checks actual desktop URI support; run it in the user's interactive desktop. Registration seen in an Agent process is not proof that another desktop can launch it.

This generic queue is a local file adapter, not a universal live CloudBase worker. Existing cloud deployments must connect their own queue adapter and schema explicitly; copying frontend files does not migrate cloud tables. No private production endpoint or credentials are included.
