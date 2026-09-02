# V3 implementation report (not a release)

## Scope completed

- The unique anonymous workbench template now has local-first training-set,
  cardio, and nutrition screens. Training records retain the plan separately
  from actual sets; cardio supports stairs, run, swim, and custom activity.
- Meal records separate pre-meal estimate, after-meal consumed candidate, and
  `confirmed_nutrition`. Nothing is booked until the user confirms it.
- `integrations/cloudbase` contains a disabled anonymous config example,
  owner-only RLS migration, and documentation for optional self-hosting.
- The public local Agent has no credential, database endpoint, scheduler, or
  model client. Its default is one explicit check; an explicit diagnostic watch
  is capped at 10 minutes, 3 empty checks, and 3 failures.
- The web contract accepts only a known job id and performs exactly one status
  read after an explicit user refresh. It has no recurring timer or visibility
  listener.
- The workbench now includes completed-training calendar/history, revisioned
  set corrections, add/remove-set controls, nutrition macro adjustment/undo,
  subjective check-ins, and a local-archive queue contract.
- `lzheng-nutrition-system` is the eighth portable Skill. Bootstrap writes an
  anonymous schema-2 contract with profile values left `null`, and the builder
  projects the confirmed contract into `workbench-data`.
- The optional Windows protocol accepts only `lzheng-fitness-agent://run`,
  reads installation-time private paths, and starts one hidden `-Once` run. It
  creates no scheduler or login trigger.

## Tests run

| Command | Result |
| --- | --- |
| `powershell -NoProfile -ExecutionPolicy Bypass -File integrations/cloudbase/local-agent/Test-LocalAgentSafety.ps1` | exit 0; `passed: true`, 0 triggers, 0 empty-queue model calls |
| `powershell -NoProfile -ExecutionPolicy Bypass -File integrations/cloudbase/local-agent/Test-LocalAgentConcurrency.ps1` | exit 0; two processes produced exactly one adapter call |
| `python skills/lzheng-nutrition-system/scripts/validate_nutrition_contract.py ...` | exit 0; `NUTRITION_CONTRACT: PASS` |
| `python skills/lzheng-nutrition-system/scripts/test_nutrition_system.py` | exit 0; `NUTRITION_SYSTEM_TEST: PASS` |
| `python skills/lzheng-fitness-workbench-builder/scripts/Initialize-FitnessWorkbench.py --target <隔离目录> --brand TRAIN --athlete 使用者 --start-date 2026-08-31` | exit 0; `FITNESS_WORKBENCH_INIT: PASS`, checker PASS, anonymous demo only |
| `python skills/lzheng-fitness-workbench-builder/scripts/Validate-FitnessWorkbenchSkill.py --skill ...` | exit 0; `FITNESS_WORKBENCH_SKILL: PASS`, 80 files |
| `python tools/validate_bundle.py` | exit 0; `OK: Lzheng Fitness bundle is portable, renderable, and installable.`; `Validated Skills: 8` |
| `python integrations/cloudbase/Test-MigrationContract.py` | exit 0; required columns/RPC/RLS plus missing-column and missing-RPC negative fixtures PASS |
| `python integrations/cloudbase/Test-InstanceIsolation.py` | exit 0; anonymous instance and plan-version storage scopes do not collide |
| Template / integration privacy search for private absolute paths and file/deep-link URIs | PASS; no matches after template cleanup |

The full bundle suite completed with exit 0. Independent acceptance still
remains required before any release, deployment, or publication claim.

## Privacy and isolation

The added integration folder contains no user name, account, phone, endpoint,
environment id, credential, photo, personal path, training record, or Notion
identifier. The isolated bootstrap used an anonymous athlete and generated
demo data only. The public template no longer has an Obsidian deep-link path.

## Deliberate acceptance boundaries

- No CloudBase project was configured, queried, migrated, deployed, uploaded,
  or published.
- No real account, cross-device sync, real queue claim, model call, or photo
  recognition was performed. Those require a user's private adapter and manual
  acceptance.
- This report proves repository-local QA for the anonymous v3.1.0 source.
  Merging or pushing the source does not imply a GitHub Release, CloudBase
  deployment, real-account acceptance, or online verification.

## Status terms

`formal_refreshed`, `release_prepared`, `deployed`, and `online_verified`
remain distinct. This work proves only local code and isolated initialization;
it does not claim a release, deployment, or online verification.
