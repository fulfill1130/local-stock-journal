# Documentation Index

This index organizes project documentation before Desktop Product Track implementation. It is documentation only and does not change runtime behavior.

## Core Contracts

Core documents describe shared contracts that should outlive any single UI shell:

- [Core README](core/README.md)
- [Architecture](ARCHITECTURE.md)
- [Data Model](DATA_MODEL.md)
- [Import Pipeline](IMPORT_PIPELINE.md)
- [Import Staging Specification](IMPORT_STAGING_SPEC.md)
- [Corporate Actions Specification](CORPORATE_ACTIONS_SPEC.md)
- [Desktop Data Architecture](DESKTOP_DATA_ARCHITECTURE.md)

Core contracts should not depend on Flask templates, static JavaScript, or desktop shell implementation details.

## Web Prototype Track

The current Flask app remains the feature lab and validation surface:

- [Web Prototype README](web_prototype/README.md)
- [Development Tracks](DEVELOPMENT_TRACKS.md)
- [Framework Direction](FRAMEWORK_DIRECTION.md)
- [Stock Detail Page Requirements](STOCK_DETAIL_PAGE_REQUIREMENTS.md)

## Desktop Product Track

Desktop Product documents describe the final software direction:

- [Desktop Product README](desktop_product/README.md)
- [Desktop Product Plan](desktop_product/PLAN.md)
- [Desktop Product Log](desktop_product/PRODUCT_LOG.md)
- [Desktop Shell Interface](DESKTOP_SHELL_INTERFACE.md)
- [Desktop Data Architecture](DESKTOP_DATA_ARCHITECTURE.md)

## Providers And Data Sources

Provider documents describe optional data-source adapters and safety rules:

- [Providers README](providers/README.md)
- [Market Data Providers](MARKET_DATA_PROVIDERS.md)

## Safety And Privacy

- [Security and Privacy](SECURITY_AND_PRIVACY.md)
- [Disclaimer](DISCLAIMER.md)
- [Runtime Config Inventory](RUNTIME_CONFIG_INVENTORY.md)

## Public Release And Project History

- [Product Vision](PRODUCT_VISION.md)
- [Roadmap](ROADMAP.md)
- [Public Release Checklist](PUBLIC_RELEASE_CHECKLIST.md)
- [Framework Migration Plan](FRAMEWORK_MIGRATION_PLAN.md)
- [Migration Log](MIGRATION_LOG.md)
- [Open Source Migration Log](OPEN_SOURCE_MIGRATION_LOG.md)
- [Plugin System Draft](PLUGIN_SYSTEM_DRAFT.md)
