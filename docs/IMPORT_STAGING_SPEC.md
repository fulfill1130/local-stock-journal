# Import Staging Specification

This is a draft specification for AI-assisted broker document import. It is a design document only; it does not describe implemented runtime behavior.

The goal is to help users convert broker PDFs, images, or copied text into reviewable staging rows without giving the app trading permissions or direct uncontrolled access to private data.

## Intended Flow

1. The user selects a broker PDF, image, screenshot, or copied text.
2. The user may crop or select a safe region before sharing anything with an AI tool.
3. The user sends the cropped content or extracted text to their chosen AI tool.
4. The AI returns a fixed structured JSON format.
5. The user pastes the JSON result back into the app.
6. The app validates the pasted result into import staging.
7. The user reviews warnings, missing fields, suspicious values, and duplicate candidates.
8. Only after explicit confirmation does the app write accepted rows to the account ledger.

## Draft AI Result Shape

```json
{
  "source_type": "broker_pdf",
  "broker": "example_broker",
  "account_label": "optional local label",
  "transactions": [
    {
      "time": "2026-06-26T09:30:00+08:00",
      "date": "2026-06-26",
      "action": "BUY",
      "ticker": "DEMOA",
      "name": "Demo Stock A",
      "shares": 100,
      "price": 20.15,
      "fee": 1,
      "tax": 0,
      "amount": 2016,
      "note": "Parsed from demo broker statement"
    }
  ],
  "dividend_movements": [
    {
      "date": "2026-06-20",
      "ticker": "DEMOA",
      "name": "Demo Stock A",
      "amount": 35,
      "tax": 0,
      "fee": 0,
      "note": "Cash dividend received"
    }
  ],
  "cash_movements": [
    {
      "date": "2026-06-26",
      "type": "deposit",
      "amount": 10000,
      "currency": "TWD",
      "note": "Optional cash movement"
    }
  ],
  "warnings": [
    "Example warning: confirm whether fee is already included in amount."
  ],
  "raw_text": "Optional pasted or extracted source text retained for review.",
  "needs_review": true
}
```

## Transaction Fields

Required transaction fields:

- `time` or `date`: trade timestamp or trade date.
- `action`: `BUY` or `SELL`.
- `ticker`: instrument ticker code.
- `shares`: traded quantity.
- `price`: execution price.
- `fee`: broker fee, use `0` only when the source clearly says none.
- `tax`: transaction tax, use `0` only when the source clearly says none.
- `amount`: total cash amount from the source.

Optional transaction fields:

- `name`: instrument name.
- `note`: user-readable source note or parser note.

## Dividend Movement Fields

Dividend movement rows represent actual account cash received, not estimated dividend calendar data.

Recommended fields:

- `date`: received date.
- `ticker`: instrument ticker code.
- `name`: optional instrument name.
- `amount`: actual received cash amount.
- `tax`: tax withheld, if available.
- `fee`: broker or handling fee, if available.
- `note`: source note or parser note.

## Validation Principles

- Never write AI or parser output directly to the final ledger.
- Require human review before confirmed ledger writes.
- Highlight missing, ambiguous, or suspicious fields.
- Preserve the original pasted JSON and optional source text for review where practical.
- Detect duplicate candidates using stable fields such as date, action, ticker, shares, price, fee, tax, and amount.
- Treat broker statements and official broker records as the source of truth when AI output conflicts with source documents.
- Keep estimated dividend calendar data separate from actual received dividend records.

Suspicious examples:

- Missing ticker, action, shares, price, or amount.
- Negative fee or tax.
- `BUY` or `SELL` actions outside the allowed set.
- Amount that does not reconcile with `shares * price`, fee, and tax.
- Dividend rows mixed into trade transactions.
- Multiple rows that appear to describe the same broker order.

## Privacy And Permissions

This flow avoids giving the app trading permissions because imports only create staging rows until the user confirms them. The app should not connect to broker trading APIs, place orders, or treat AI output as an instruction to trade.

This flow also avoids giving the app direct uncontrolled AI access to private data. The user chooses what to crop, redact, copy, or send to an AI tool. The app receives the structured result only when the user pastes it back, then validates it locally before any ledger write is possible.

## Current Status

This specification is a public draft. Existing upload and PDF text extraction surfaces are local and early-stage. A complete staging UI, validator, duplicate review screen, and final confirmation flow still need separate implementation work.
