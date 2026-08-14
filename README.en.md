# Lzheng Fitness Skills

Portable, offline-first Agent Skills for a personal training system. Version 2.0 adds a system controller and a responsive local workbench to the existing planning, return-to-training, cycle-design, and review Skills.

The public bundle contains no personal training records, account data, or fixed machine paths. It includes the Garou workbench artwork with authorization from this repository's maintainer, so a new computer can run the workbench fully offline.

## Skills

- `lzheng-fitness-plan`: intake, safety routing, programming, and standalone plan HTML.
- `lzheng-training-return`: return-to-training after interruption or changed conditions.
- `lzheng-strength-cycle-planner`: an 8–12 week cycle for one strength lift.
- `lzheng-strength-training-review`: single-session, rolling, baseline, and weekly training review.
- `lzheng-training-system`: bootstrap, migration, diagnostics, protected upgrades, and suite validation.
- `lzheng-fitness-workbench-builder`: builds a responsive offline workbench from plans, reviews, and optional dynamic-data input.

Python 3.10+ is required; no third-party Python package is needed.

## Install and verify

```bash
python tools/install.py --platform codex --all
python tools/validate_bundle.py
```

For an isolated target:

```bash
python tools/install.py --target-root ./test-agent --all
python <skills-dir>/lzheng-training-system/scripts/lzheng_training_system.py bootstrap --target "<empty-folder>"
python <skills-dir>/lzheng-training-system/scripts/lzheng_training_system.py doctor --root "<empty-folder>"
```

`bootstrap` only accepts an empty directory and creates an anonymous demonstration system. Replace its example plan with a confirmed plan before real training. The resulting `个人训练系统/健身工作台.html` is responsive and has no online runtime dependency.

The installer refuses to overwrite an existing Skill unless `--force` is supplied; it creates a backup before replacement.

This project supports general training planning and record keeping. It is not medical diagnosis or rehabilitation advice. See [the evidence register](knowledge/06-lzheng-source-register.md) and [asset notice](ASSET-NOTICE.md).

MIT © 2026 Lzheng
