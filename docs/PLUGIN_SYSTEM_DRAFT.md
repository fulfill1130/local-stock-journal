# Plugin System Draft

This is a draft specification for a future plugin system. Plugin loading is not implemented yet.

The long-term goal is to let users connect external open-source analysis tools, market data adapters, reports, and assistant rules while keeping the stock journal local-first and ledger-safe.

Plugin outputs are advisory or research notes only. They are not investment advice, trading instructions, tax advice, or legal advice.

## First-Version Principles

- Read-first by default.
- No trading permissions.
- No broker trading API access.
- No automatic order placement.
- No direct writes to confirmed ledger records.
- Explicit user consent before a plugin receives private account data.
- Explicit user review before any plugin output can become a ledger change.
- Local data boundaries must be clear: plugins receive only the data the user chooses to provide.
- Permission requests should be small, understandable, and scoped to a specific task.

## Draft Manifest Shape

```json
{
  "name": "example_research_plugin",
  "version": "0.1.0",
  "description": "Summarizes local position and K-line context for one ticker.",
  "author": "Example Author",
  "entrypoint": "python -m example_plugin",
  "permissions": [
    "read:ticker",
    "read:holding_summary",
    "read:ohlcv_history"
  ],
  "supported_inputs": [
    "ticker",
    "profile_summary",
    "holding_summary",
    "transactions",
    "dividends",
    "ohlcv_history",
    "notes"
  ],
  "output_type": "research_note"
}
```

## Permission Ideas

Initial permissions should be read-only and explicit:

- `read:ticker`
- `read:profile_summary`
- `read:holding_summary`
- `read:transactions`
- `read:dividends`
- `read:ohlcv_history`
- `read:notes`
- `write:staging_note`

Direct confirmed ledger writes should not be part of the first plugin version.

## Possible Plugin Input JSON

```json
{
  "ticker": "DEMOA",
  "profile_summary": {
    "profile": "demo",
    "currency": "TWD",
    "total_market_value": 250000,
    "cash_available": 10000
  },
  "holding_summary": {
    "ticker": "DEMOA",
    "name": "Demo Stock A",
    "shares": 120,
    "avg_cost": 19.8,
    "market_value": 2520,
    "unrealized_pnl": 144,
    "portfolio_weight": 0.01
  },
  "transactions": [
    {
      "time": "2026-04-01",
      "action": "BUY",
      "ticker": "DEMOA",
      "shares": 100,
      "price": 19.5,
      "fee": 1,
      "tax": 0,
      "amount": 1951
    }
  ],
  "dividends": [
    {
      "date": "2026-06-20",
      "ticker": "DEMOA",
      "amount": 35,
      "note": "Actual received dividend"
    }
  ],
  "ohlcv_history": [
    {
      "date": "2026-06-26",
      "open": 20.5,
      "high": 21.2,
      "low": 20.3,
      "close": 21,
      "volume": 120000
    }
  ],
  "notes": [
    {
      "date": "2026-06-26",
      "text": "User-written local note."
    }
  ]
}
```

## Possible Plugin Output JSON

```json
{
  "title": "DEMOA local position review",
  "summary": "The position is above average cost in the provided local data.",
  "observations": [
    "Latest close is above the provided average cost.",
    "Recent volume is within the local sample range."
  ],
  "risks": [
    "Sample data is synthetic and should not be used for real decisions."
  ],
  "signals": [
    {
      "label": "trend_context",
      "value": "above_cost",
      "confidence": "low",
      "reason": "Derived only from provided local sample data."
    }
  ],
  "warnings": [
    "This output is a research note, not investment advice."
  ],
  "generated_at": "2026-06-26T12:00:00+08:00"
}
```

## Output Rules

- Plugin output should be displayed as a research note.
- Output must not be treated as financial advice or a trading signal.
- Output must not trigger orders, broker actions, or confirmed ledger writes.
- If a plugin suggests a ledger correction, it should produce a reviewable staging item only.
- The app should keep source labels, timestamps, and warnings visible.

## Current Status

The plugin system is a long-term direction. Current public code contains provider and registry foundations, but no general plugin loader, plugin sandbox, permission manager, or external tool execution flow.
