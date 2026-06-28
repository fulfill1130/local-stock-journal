# Web Stock Machine

Purpose:

- Future home for the web prototype / Flask stock machine.
- Feature lab and validation surface for workflows before they are promoted to the desktop product.

What belongs here:

- Web prototype app structure after a future planned move.
- Flask-specific routes, templates, static assets, and web-only development notes.
- Web validation surfaces for accounting, imports, market data, ETF holdings, and provider flows.

What must not belong here:

- Final desktop app shell or desktop-first UI code.
- Real user account data, private profiles, credentials, provider secrets, logs, backups, or raw provider responses.
- Shared market database runtime data.

Current status:

- Placeholder/future home only.
- No runtime code has been moved yet.
- The current root runtime is the legacy web prototype/reference and still remains in the existing source layout.
- The web prototype remains a feature lab.
- The web UI is not the final desktop UI.
- See [Legacy Web Prototype](LEGACY_WEB_PROTOTYPE.md).

What currently lives elsewhere:

- Current Flask routes and app composition remain in the existing `src/` layout.
- Current Flask templates remain in `src/templates/`.
- Current static assets remain in `src/static/`.
- Current web/prototype docs remain under `docs/`.

Current related docs:

- [Legacy Web Prototype](LEGACY_WEB_PROTOTYPE.md)
- [Web Prototype Track](../docs/web_prototype/README.md)
- [Stock Detail Page Requirements](../docs/STOCK_DETAIL_PAGE_REQUIREMENTS.md)
- [Import Pipeline](../docs/IMPORT_PIPELINE.md)
- [Architecture](../docs/ARCHITECTURE.md)
- [Framework Direction](../docs/FRAMEWORK_DIRECTION.md)

What may move here later:

- Flask-specific routes, templates, static files, and web-only docs after a planned source layout task.
- Web prototype fixtures or examples that are not shared core contracts.

Source/runtime movement is deferred.
