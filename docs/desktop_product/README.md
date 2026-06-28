# Desktop Product Track

The Desktop Product Track is the final software direction.

The desktop product should:

- Rebuild the app shell, navigation, and UI from scratch.
- Reuse core contracts, safety rules, and proven logic from the web prototype.
- Use an explicit app data root.
- Keep demo and real data separate.
- Require backup and dry-run before any real profile migration.
- Keep provider fetches manual-trigger unless a future task explicitly changes that.
- Keep imports, AI output, plugins, and corporate action proposals in staging/review before final writes.

Current documents:

- [Plan](PLAN.md)
- [Product Log](PRODUCT_LOG.md)
- [Desktop Shell Interface](../DESKTOP_SHELL_INTERFACE.md)
- [Desktop Data Architecture](../DESKTOP_DATA_ARCHITECTURE.md)

Possible future source-code separation:

```text
src/desktop_app/
src/core/
src/shared/
```

Do not create or move runtime source files yet. The next phase should plan app-data-root, backup/recovery, desktop shell lifecycle, and UI boundaries before desktop implementation starts.
