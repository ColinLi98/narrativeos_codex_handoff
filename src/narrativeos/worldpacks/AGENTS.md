# Worldpacks AGENTS.md — NarrativeOS Asset Boundary

Read repo-root `AGENTS.md` first. This file narrows the rules for `src/narrativeos/worldpacks/`.

## Mission
- Keep `worldpacks/` as asset, policy, and validation territory.
- Make pack weaknesses easier to diagnose and improve without leaking into `core/`.

## Do
- Improve pack schema, registry behavior, validation, and capability asset structure.
- Keep assets legible to Author / Ops tooling and benchmark diagnostics.
- Prefer changes that help weakest packs or improve cross-pack maintainability.

## Do not
- Move generic engine logic into pack assets.
- Hide behavioral fixes in one pack instead of exposing missing capabilities.
- Present pack-local prose tuning as platform progress.

## Validation
- Run tests touching registry / validation / runtime assembly.
- Run cross-pack benchmark when asset structure or runtime assembly changes.
- Update benchmark sample or docs when output-facing asset diagnostics change.
