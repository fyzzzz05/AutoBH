# AutoBH workspace

Use local Git commits as checkpoints for completed, verified work so source changes can be rolled back. Do not create or retain historical App bundles or compressed rollback backups after a successful installation. Follow the detailed GUI and packaging instructions in `gui/AGENTS.md` and `scripts/AGENTS.md`.

Keep credentials, account data, runtime caches, dependencies and generated installers out of Git. AutoSign, AutoBoya and AutoTD source snapshots are ordinary files in this repository; preserve their separate local `.git` directories and histories. Do not push or publish to GitHub unless the user requests it.
