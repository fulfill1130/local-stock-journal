# Corporate Actions Specification

This is a planning-only specification. It does not describe implemented runtime behavior and does not change accounting, market data, import staging, or UI behavior.

Corporate actions can affect shares, lots, cost basis, and cash. The project should treat market announcements as useful alerts, but the user's broker/account settlement remains the final accounting source of truth.

## Core Rule

Corporate action notices are alerts and theoretical calculations only.

Broker/account settlement results are the final accounting source of truth.

The app must not automatically modify the final ledger, holdings, lots, or cash based only on announcements, provider data, API data, AI output, or estimated terms.

## Corporate Action Notice

A corporate action notice represents market, API, exchange, company, or provider announcement data.

Draft fields:

```json
{
  "ticker": "DEMOA",
  "action_type": "split",
  "announcement_date": "2026-06-01",
  "record_date": "2026-06-10",
  "effective_date": "2026-06-15",
  "theoretical_ratio": "2:1",
  "terms": "Two new shares for each one old share.",
  "source": "example_provider",
  "status": "announced",
  "notes": "Planning example only."
}
```

Rules:

- A notice may create an alert or pending review item.
- A notice may support theoretical share and cost-basis previews.
- A notice must not directly write confirmed transactions, cash movements, lots, holdings, or final ledger records.
- A notice must not be treated as proof that the user's broker delivered the same result.

## Corporate Action Settlement

A corporate action settlement represents the user's broker/account reality after the action is actually processed.

Draft fields:

```json
{
  "ticker": "DEMOA",
  "profile": "demo",
  "action_type": "split",
  "old_shares": 100,
  "theoretical_new_shares": 200,
  "delivered_shares": 200,
  "cash_in_lieu": 0,
  "broker_settlement_date": "2026-06-17",
  "confirmed_at": "2026-06-18T10:00:00+08:00",
  "source": "broker_statement",
  "notes": "User-confirmed settlement."
}
```

Rules:

- Settlement is the only corporate action object allowed to affect final accounting.
- Settlement must require explicit user confirmation before any final ledger or rebuild effect.
- Settlement source should be a broker statement, account activity record, or user-confirmed broker result.
- Cash settlement must be represented separately and linked to the settlement.

## Supported Action Types

Future work should support these action types explicitly:

- `split`
- `reverse_split`
- `capital_reduction`
- `stock_dividend`
- `rights_issue`
- `merger_or_conversion`
- `cash_in_lieu`

Each action type needs its own accounting rules. Cost basis treatment, share conversion, cash movement handling, and lot rebuild behavior must be explicit per action type.

## Hit Detection And Review

When a notice is imported or discovered:

- If a profile held the ticker around the relevant record or effective date, create a pending review item for that profile.
- If the profile did not hold the ticker during the relevant window, keep the notice as market history only.
- Watchlist or search-only instruments may show informational notices, but they should not create account settlement records.
- Hit detection should be conservative. Ambiguous cases should require user review rather than automatic accounting action.

## Fractional Shares And Cash In Lieu

Fractional-share behavior is broker-specific and must not be guessed.

Rules:

- The app may calculate theoretical fractional shares.
- The app must not guess delivered shares.
- The app must wait for a broker statement or user-confirmed actual result.
- Cash-in-lieu is user/broker supplied, not estimated by the app.
- Any difference between theoretical shares and delivered shares should be visible in the review record.

## Accounting Philosophy

- Original trades remain immutable.
- Corporate action settlements are confirmed accounting events.
- Derived holdings and FIFO lots should be rebuilt from original trades plus confirmed settlements.
- Cost basis treatment must be explicit per action type.
- Cash settlements are separate cash movements linked to the settlement.
- Rebuild logic should make the effect reviewable and repeatable.
- No provider or market notice should silently rewrite historical trades.

## Relationship To Import Staging

Corporate action notices are similar to unconfirmed import results: they may be useful, but they are not final accounting records.

Corporate action settlements are similar to user-approved import rows: they may affect accounting only after review and confirmation.

Any future provider, AI parser, broker document parser, or plugin that proposes a corporate action must produce a reviewable staging item first. It must not write directly to the final ledger.

## Non-Goals

- No automatic ledger writes from API notices.
- No automatic holdings, lots, or cash changes from announcements.
- No guessing fractional-share rounding behavior.
- No immediate provider or API integration.
- No UI implementation in this specification.
- No migration of existing local profile data.
- No broker trading API integration.
- No trading advice or automatic order placement.

## Future Implementation Notes

The safest future path is:

1. Store notices as market/history data.
2. Detect profile hits and create pending review items.
3. Let users enter or import broker-confirmed settlement results.
4. Validate settlement rows in staging.
5. Apply confirmed settlements through explicit rebuild logic only after user approval.
