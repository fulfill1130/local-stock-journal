# Core Contracts

Core is the shared product foundation. It should be reusable by the Web Prototype Track and the Desktop Product Track.

Core includes:

- Shared accounting contracts.
- Market data contracts.
- ETF holdings snapshot and provider contracts.
- Import staging contracts.
- Corporate action notice and settlement contracts.
- Storage and data-root contracts.
- Local-first privacy, demo/real separation, and reviewed-write safety rules.

Core must not depend on:

- Flask page routes.
- Flask templates.
- Static JavaScript UI.
- Desktop shell/window implementation.
- pywebview, Tauri, Electron, or packaging decisions.

Current related documents:

- [Architecture](../ARCHITECTURE.md)
- [Data Model](../DATA_MODEL.md)
- [Import Pipeline](../IMPORT_PIPELINE.md)
- [Import Staging Specification](../IMPORT_STAGING_SPEC.md)
- [Corporate Actions Specification](../CORPORATE_ACTIONS_SPEC.md)
- [Desktop Data Architecture](../DESKTOP_DATA_ARCHITECTURE.md)
- [Market Data Providers](../MARKET_DATA_PROVIDERS.md)

Future source-code separation may introduce:

```text
src/core/
src/shared/
```

Do not move runtime source files until the data-root, backup, import staging, and desktop shell boundaries are explicitly planned and tested.
