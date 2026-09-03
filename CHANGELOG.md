# Changelog

## Unreleased

- Fixed CI invoking Windows PowerShell on Ubuntu. Both Ubuntu and Windows now
  run the portable bundle gates; Windows also runs the required local-Agent
  safety and concurrency processes. Added regression coverage for platform
  routing and fail-closed behavior when Windows PowerShell is missing.
- Fixed regression-fixture cleanup to unlink POSIX directory symlinks and
  remove Windows junctions without touching their target directories.

## 3.1.0 — 2026-09-02

- Added the v3 anonymous local-first recorder: plan snapshots and actual sets
  are separated, cardio supports stairs/run/swim/custom entries, and the meal
  flow keeps pre-meal estimates, after-meal candidates, and user confirmation
  distinct.
- Added an optional generic CloudBase adapter with owner-only RLS, disabled
  example configuration, and a public local Agent boundary that has no trigger,
  startup work, or model call on an empty queue.
- Added the eighth portable Skill, `lzheng-nutrition-system`, with an anonymous
  schema-2 nutrition contract and a strict estimate → consumed candidate →
  user-confirmed ledger boundary.
- Added training calendar/history correction with revision snapshots, nutrition
  macro adjustment/undo, subjective check-ins, and an explicit local-archive
  queue contract. The web now performs one task-status read per user refresh;
  no background polling window remains.
- Added an optional Windows protocol handoff that registers only after an
  explicit install command and starts one hidden `-Once` run. It creates no
  scheduler, login trigger, or browser-supplied local path.

- Added a compact read-only workbench inspector and token-efficient plan revision route so routine agents read current JSON/Markdown sources instead of the 100 KB+ generated HTML and unrelated publishing references.
- Added fixed workbench shell validation so a missing desktop sidebar/mobile bottom navigation can no longer pass the formal checker or UI contract gate.
- Removed the five-review projection cap so every valid review indexed by the user is retained in the workbench, with regression coverage for count and order.
- Added an end-to-end plan-change regression proving routine refreshes change only `workbench-data`, preserve the entire sidebar/view shell byte-for-byte, and reject a missing navigation container.
- Made compact training-system inspection strictly read-only, aligned the workbench navigation contract to `指南`, and preserved review links on actual chart points.
- Added an evidence-backed one-command workbench refresh pipeline with separate formal-refresh, local-release, deployment, and online-verification claims.
- Added incremental/full Notion snapshot semantics, full-date history keys, conflict detection, and regression coverage that preserves verified session and main-lift history across refreshes and training cycles.
- Added manifest-owned private and public-anonymized release modes, exact-tree and hash validation, Windows junction/reparse protection, and an identity-neutral public shell that cannot copy personal media.
- Added installer drift verification, external recoverable backups, and path-containment protections for managed Skill destinations.

## 2.3.1 — 2026-08-21

- Added a supported background-replacement command for generated workbenches: static PNG/JPEG/WebP mode or MP4 mode with a required image fallback.
- Added automatic HTML/asset backups, safe desktop/mobile crop controls, post-change validation, and rollback when validation fails.
- Added first-initialization background arguments and regression coverage for static/video replacement, damaged inputs, renamed folders, and release copies.

## 2.3.0 — 2026-08-21

- Upgraded the offline workbench to the fixed v3 interface with a local motion background, static fallback, responsive layouts, and an in-workbench reader for reviews and status documents.
- Replaced machine-bound system configuration with current-root-relative paths and a runtime Skill marker; legacy absolute paths now migrate automatically with a recoverable configuration backup.
- Expanded portability checks to cover renamed folders, Chinese and spaced paths, no-Obsidian release copies, embedded documents, plan targets, CSS/images/video/posters, and explicit missing-asset failures.
- Kept personal training data, machine paths, preview screenshots, caches, and generated review copies outside the public bundle.

## 2.2.0 — 2026-08-17

- Added a seventh portable Skill containing six complete source-limited expert modules: Alan Aragon, Brad Schoenfeld, Brukner and Khan, Dan John, Eric Helms, and Greg Nuckols.
- Added explicit source/version boundaries, coverage and decision artifacts, knowledge cards, variable-based minimum-expert selection, safety triage, honest validation states, and deterministic route tests.
- Wired plan, cycle, review, and return Skills to the shared expert library; installing any of those Skills now installs the library automatically.
- Kept raw books, article snapshots, private training data, and machine-specific paths outside the public bundle.

## 2.1.2 — 2026-08-17

- Added an atomic week-transition contract: weekly review updates the current schedule before handoff and workbench refresh.
- Added a portable regression gate for stale dates, mixed week labels, declared-frequency mismatches, missing today prescriptions, and selfweight overwritten by history.
- Preserved public templates and anonymous assets; this release changes data integrity rules, not personal training data or visual identity.

## 2.1.1 — 2026-08-14

- Added fixed goal-data cards to the workbench: hypertrophy distinguishes planned muscle-group sets from completed work, while fat loss tracks only recorded bodyweight, steps, and cardio data.
- Added `tracking_targets` to the plan contract and guided intake so target-specific metrics, their sources, and missing baselines are explicit rather than invented.
- Added optional activity records (`steps`, `cardio_minutes`) to the portable Notion input contract.

## 2.1.0 — 2026-08-14

- Made AI-led onboarding the primary first-use path for users starting hypertrophy, fat-loss, strength, or general-fitness systems; README and command lookup are no longer the required entry point.
- Added per-exercise verified-load, calibration, and non-weight progression states so unknown weights become guided calibration rather than user guesswork.
- Added a `plan_contract` adapter so complete plans can initialize the workbench without a separately hand-authored four-lift plan format.
- Rebuilt the complete-plan navigation around five fixed execution entries and added an HTML audit for the fixed navigation contract.
- Standardized the workbench’s offline Garou visual requirement while keeping standalone plan pages on their separate fixed plan visual contract.

## 2.0.0 — 2026-08-14

- Added `lzheng-training-system` for portable bootstrap, diagnosis, protected upgrades, handoff processing, and suite-level validation.
- Added `lzheng-fitness-workbench-builder` for an offline, responsive training workbench with desktop, tablet, and mobile layouts.
- Added an isolated bootstrap-and-doctor release check to the bundle validator.
- Included authorized Garou background assets so generated workbenches work offline on another computer.
- Kept personal records, private paths, and live training data out of the public bundle.

## 1.1.0

- Added weekly training review workflow.
