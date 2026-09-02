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
