from __future__ import annotations

import base64
import hashlib
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from central_store import (
    get_gmail_attachment_receipt,
    get_gmail_statement_receipt,
    record_gmail_attachment_receipt,
    record_operation_log,
    record_uploaded_document,
)


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
BROKER_STATEMENT_SUBJECT = re.compile(
    r"^台新證券\s+20\d{2}\.\d{1,2}\.\d{1,2}\s+交割憑單$"
)


def gmail_service(credentials_path: Path, token_path: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Gmail dependencies are missing. Run: pip install -r requirements.txt"
        ) from exc

    if not credentials_path.exists():
        raise FileNotFoundError(f"Gmail credentials not found: {credentials_path}")

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_path), [GMAIL_READONLY_SCOPE]
        )

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), [GMAIL_READONLY_SCOPE]
            )
            credentials = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def list_matching_messages(
    credentials_path: Path,
    token_path: Path,
    query: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    service = gmail_service(credentials_path, token_path)
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max(1, min(max_results, 100)))
        .execute()
    )
    rows: list[dict[str, Any]] = []
    for item in response.get("messages", []):
        message = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="full")
            .execute()
        )
        payload = message.get("payload") or {}
        headers = {
            str(header.get("name") or "").lower(): str(header.get("value") or "")
            for header in payload.get("headers", [])
        }
        attachments = attachment_names(payload)
        rows.append(
            {
                "message_id": message.get("id", ""),
                "thread_id": message.get("threadId", ""),
                "date": headers.get("date", ""),
                "from": headers.get("from", ""),
                "subject": headers.get("subject", ""),
                "attachments": attachments,
            }
        )
    return rows


def attachment_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    stack = [payload]
    while stack:
        part = stack.pop()
        filename = str(part.get("filename") or "").strip()
        if filename:
            names.append(filename)
        stack.extend(part.get("parts") or [])
    return names


def pdf_attachment_parts(payload: dict[str, Any]) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    stack = [payload]
    while stack:
        part = stack.pop()
        filename = str(part.get("filename") or "").strip()
        body = part.get("body") or {}
        attachment_id = str(body.get("attachmentId") or "").strip()
        if filename.lower().endswith(".pdf") and attachment_id:
            attachments.append(
                {
                    "filename": filename,
                    "attachment_id": attachment_id,
                    "mime_type": str(part.get("mimeType") or "application/pdf"),
                }
            )
        stack.extend(part.get("parts") or [])
    return attachments


def statement_date_from_text(*values: str) -> str:
    patterns = (
        re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)"),
        re.compile(r"(?<!\d)(20\d{2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)"),
    )
    for value in values:
        for pattern in patterns:
            match = pattern.search(str(value or ""))
            if not match:
                continue
            try:
                return date(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                ).isoformat()
            except ValueError:
                continue
    return ""


def sync_latest_pdf_attachments(
    project_root: Path,
    central_db_path: Path,
    *,
    profile_slug: str,
    credentials_path: Path,
    token_path: Path,
    query: str,
    max_results: int = 20,
    all_missing: bool = False,
) -> dict[str, Any]:
    service = gmail_service(credentials_path, token_path)
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max(1, min(max_results, 100)))
        .execute()
    )
    candidates: list[dict[str, Any]] = []
    for item in response.get("messages", []):
        message = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="full")
            .execute()
        )
        payload = message.get("payload") or {}
        headers = {
            str(header.get("name") or "").lower(): str(header.get("value") or "")
            for header in payload.get("headers", [])
        }
        if not BROKER_STATEMENT_SUBJECT.fullmatch(headers.get("subject", "").strip()):
            continue
        for attachment in pdf_attachment_parts(payload):
            attachment["message_id"] = str(message.get("id") or "")
            attachment["subject"] = headers.get("subject", "")
            attachment["statement_date"] = statement_date_from_text(
                attachment["filename"], headers.get("subject", "")
            )
            candidates.append(attachment)

    dated = [row for row in candidates if row["statement_date"]]
    if dated and not all_missing:
        latest_date = max(row["statement_date"] for row in dated)
        candidates = [row for row in dated if row["statement_date"] == latest_date]

    summary = {
        "matched_messages": len(response.get("messages", [])),
        "candidate_pdfs": len(candidates),
        "stored": 0,
        "duplicate_message": 0,
        "duplicate_hash": 0,
        "date_conflict": 0,
        "failed": 0,
        "files": [],
    }
    today = date.today().isoformat()
    for candidate in candidates:
        message_id = candidate["message_id"]
        attachment_id = candidate["attachment_id"]
        filename = candidate["filename"]
        statement_date = candidate["statement_date"]
        if statement_date and statement_date > today:
            summary["failed"] += 1
            summary["files"].append({"filename": filename, "status": "future_date"})
            continue
        existing = get_gmail_attachment_receipt(
            central_db_path,
            profile_slug=profile_slug,
            message_id=message_id,
            original_filename=filename,
        )
        if existing:
            summary["duplicate_message"] += 1
            summary["files"].append({"filename": filename, "status": "duplicate_message"})
            continue
        try:
            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )
            encoded = str(attachment.get("data") or "")
            payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            if not payload:
                raise ValueError("empty attachment")
            digest = hashlib.sha256(payload).hexdigest()
            date_receipt = (
                get_gmail_statement_receipt(
                    central_db_path,
                    profile_slug=profile_slug,
                    statement_date=statement_date,
                )
                if statement_date
                else None
            )
            folder_date = date.fromisoformat(statement_date) if statement_date else date.today()
            upload_dir = project_root / "data" / "uploads" / profile_slug / f"{folder_date:%Y}" / f"{folder_date:%m}"
            upload_dir.mkdir(parents=True, exist_ok=True)
            stored_path = upload_dir / f"{folder_date:%Y%m%d}_{uuid.uuid4().hex[:12]}.pdf"
            stored_path.write_bytes(payload)
            relative_path = str(stored_path.relative_to(project_root)).replace("\\", "/")
            note = f"Gmail message {message_id}; statement_date={statement_date or 'unknown'}"
            if date_receipt and str(date_receipt.get("sha256") or "") != digest:
                note += "; same statement date has different content"
            document = record_uploaded_document(
                central_db_path,
                profile_slug=profile_slug,
                original_filename=filename,
                stored_path=relative_path,
                mime_type="application/pdf",
                file_size=len(payload),
                sha256=digest,
                source="gmail",
                status="needs_review" if date_receipt and str(date_receipt.get("sha256") or "") != digest else "stored",
                note=note,
            )
            if document.get("duplicate"):
                stored_path.unlink(missing_ok=True)
                receipt_status = "duplicate_hash"
                summary["duplicate_hash"] += 1
            elif date_receipt:
                receipt_status = "date_conflict"
                summary["date_conflict"] += 1
            else:
                receipt_status = "stored"
                summary["stored"] += 1
            record_gmail_attachment_receipt(
                central_db_path,
                profile_slug=profile_slug,
                message_id=message_id,
                attachment_id=attachment_id,
                original_filename=filename,
                statement_date=statement_date,
                sha256=digest,
                upload_id=int(document["id"]),
                status=receipt_status,
                note=note,
            )
            summary["files"].append({"filename": filename, "status": receipt_status})
        except Exception as exc:
            summary["failed"] += 1
            summary["files"].append(
                {"filename": filename, "status": "failed", "error": str(exc)[:160]}
            )

    record_operation_log(
        central_db_path,
        job_name="gmail_statement_download",
        source=profile_slug,
        event_type="gmail_download",
        status="failed" if summary["failed"] else "success",
        summary=(
            f"stored={summary['stored']}; duplicate_message={summary['duplicate_message']}; "
            f"duplicate_hash={summary['duplicate_hash']}; date_conflict={summary['date_conflict']}; "
            f"failed={summary['failed']}"
        ),
    )
    return summary
