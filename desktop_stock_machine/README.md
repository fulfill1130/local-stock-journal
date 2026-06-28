# Desktop Stock Machine

Purpose:

- Future home for the desktop stock machine product.
- Final software direction for the local-first stock journal and ETF research workbench.
- Clean rebuild area for the desktop product, separate from the legacy web prototype UI.

What belongs here:

- Future desktop app shell, navigation, layout, and UI rebuilt from scratch.
- Desktop-specific product planning, app lifecycle, and data-root status surfaces after future implementation tasks.
- Desktop workflows that reuse core concepts and safety contracts without copying the current web UI.

What must not belong here:

- Current Flask web prototype code.
- Legacy Flask templates/static layout imported by default.
- Real user account data, private profiles, credentials, provider secrets, logs, backups, or raw provider responses.
- Direct writes that bypass core/storage contracts, staging, backup, or confirmation rules.

Current status:

- Placeholder/future home only.
- No desktop runtime code has been moved or implemented here yet.
- Packaging, installer, migration, and real-profile support remain future work.
- Desktop shell, navigation, layout, and UI will be rebuilt from scratch.
- Desktop work should not import or copy the legacy web UI by default.
- Real data migration requires dry-run, backup, confirmation, and verification.

What currently lives elsewhere:

- Demo-only desktop shell contracts and pywebview prototype code remain in the existing `src/` layout.
- Desktop product planning docs remain under `docs/desktop_product/`.
- Core storage and safety contracts remain under `docs/core/`.

Current related docs:

- [Desktop Product Track](../docs/desktop_product/README.md)
- [Desktop Product Plan](../docs/desktop_product/PLAN.md)
- [Desktop Data Root](../docs/desktop_product/DATA_ROOT.md)
- [Desktop Backup And Migration](../docs/desktop_product/BACKUP_MIGRATION.md)
- [Desktop Shell Interface](../docs/DESKTOP_SHELL_INTERFACE.md)
- [Storage Boundaries](../docs/core/STORAGE_BOUNDARIES.md)

What may move here later:

- Desktop app shell code, desktop navigation, desktop UI, and desktop-specific docs after planned implementation tasks.
- Desktop packaging and installer materials after the desktop product is ready.

Source/runtime movement is deferred.
