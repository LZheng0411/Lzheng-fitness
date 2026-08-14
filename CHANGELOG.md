# Changelog

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
