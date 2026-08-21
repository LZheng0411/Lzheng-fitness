# Changelog

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
