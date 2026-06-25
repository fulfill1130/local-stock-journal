# Import Pipeline

The import pipeline is designed to keep broker documents, parsed text, staging rows, and confirmed transactions separate.

The project should never let OCR or AI write directly into final account transactions without review.

## Goals

- Store broker PDFs and screenshots safely.
- Avoid duplicate imports.
- Parse documents into structured rows.
- Let the user review and edit extracted rows.
- Confirm rows into account transactions only after review.

## Recommended Flow

1. Upload file.
2. Store original file metadata.
3. Extract text or send to parser.
4. Create staging rows.
5. Detect duplicates and conflicts.
6. User reviews rows.
7. Confirmed rows become transactions.

## Upload Library

The upload library should store:

- Original filename.
- File hash.
- Upload timestamp.
- Profile target, if selected.
- Document type.
- Parse status.
- Parser message or error.

Files should be treated as private account records and excluded from public commits.

## Duplicate Detection

Use multiple keys:

- File SHA-256.
- Email message id, if downloaded from email.
- Email attachment id, if available.
- Statement date.
- Broker order number.
- Ticker.
- Trade date.
- Action.
- Shares.
- Price.

Do not deduplicate only by date, ticker, shares, and price. Same-day repeated trades can be legitimate.

## Staging Rows

Parser output should use a stable shape:

```json
[
  {
    "trade_date": "2026-06-05",
    "ticker": "0000",
    "name": "Example Security",
    "action": "BUY",
    "shares": 100,
    "price": 10.5,
    "fee": 1,
    "tax": 0,
    "order_no": "example-order-id",
    "source": "broker_statement",
    "confidence": 0.98,
    "review_status": "pending"
  }
]
```

Supported actions should include:

- `BUY`
- `SELL`

Other cash movements should be separate record types, not forced into stock trades.

## Email Attachment Download

Email integration, when configured, should use read-only access.

Responsibilities:

- Search for known statement subject patterns.
- Download attachments once.
- Store metadata.
- Avoid duplicate downloads.
- Never send or delete mail automatically.

The email downloader should not write trades directly.

## PDF Extraction

PDF extraction has two modes:

1. Text extraction from real embedded text.
2. OCR or AI parsing for image-like PDFs or screenshots.

Some broker PDFs are encrypted or rendered as images. In those cases, normal text extraction may fail even when a human can read the file.

## AI-Assisted Parsing

AI parsing can be added later as an optional parser.

Rules:

- AI receives only the document or extracted text needed for parsing.
- AI returns JSON staging rows.
- AI output is never final until the user confirms.
- Failed AI responses should be logged and shown as parse errors.
- Avoid repeated calls for the same file hash unless the user explicitly retries.

## Review UI

The review UI should show:

- Parsed rows.
- Potential duplicates.
- Missing required fields.
- Low-confidence fields.
- Conflicting rows.
- Source document link or filename.

Only confirmed rows should be written into the account transaction ledger.

## Known Constraints

- Mobile uploads can fail on unstable private network connections.
- Large PDFs should have request timeout and size handling.
- OCR is imperfect with dense broker tables.
- AI parsing costs money and should be rate-limited.
- Personal broker documents must not be committed to source control.

