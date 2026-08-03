# Lzheng Fitness Skills

Four portable Agent Skills for personalized fitness planning, return-to-training, strength-cycle design, and strength-training review. Every Skill uses the `lzheng-` namespace and includes the references required for standalone use.

## Install

Python 3.10 or newer is required. No third-party Python package is needed.

```bash
python tools/install.py --platform codex --all
python tools/install.py --platform claude --skill lzheng-fitness-plan
python tools/install.py --target-root ./test-agent --all
```

The installer refuses to overwrite an existing Skill unless `--force` is explicitly supplied. A Skill can also be installed by copying its whole folder from `skills/` into a compatible Agent skills directory.

## Skills

- `lzheng-fitness-plan`: intake, safety routing, P0–L3 classification, exercise selection, programming, and standalone HTML output.
- `lzheng-training-return`: a seven-day return path after a meaningful interruption.
- `lzheng-strength-cycle-planner`: an 8–12 week cycle for one strength lift with a standalone charted HTML plan.
- `lzheng-strength-training-review`: cycle, rolling-progression, or baseline review with a concrete next prescription.

Use `LZHENG_FITNESS_HOME` to choose a persistent output directory. Otherwise outputs are stored in `lzheng-fitness-output/` under the current working directory. Obsidian, Notion, and cloud connectors are optional, not dependencies.

## Validate

```bash
python tools/validate_bundle.py
```

The validator checks Skill metadata, local links, portable paths, script syntax, HTML generation, data consistency, and a clean installation into a temporary Agent directory.

This project provides general training-planning support, not medical diagnosis or rehabilitation. See `knowledge/06-lzheng-source-register.md` for evidence provenance.

MIT © 2026 Lzheng
