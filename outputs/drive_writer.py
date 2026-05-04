"""
Google Drive Writer -- B2Have Career Intelligence System
Authenticates via OAuth2 or service account, writes intelligence to Google Docs.
"""

import os
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("drive_writer")

ROOT = Path(__file__).parent.parent

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents"
]


def get_google_credentials():
    """Load credentials -- OAuth2 user token first, service account fallback."""
    token_file = ROOT / "config" / "token.json"

    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
                with open(token_file, "w") as f:
                    f.write(creds.to_json())
            if creds.valid:
                log.info("Using OAuth2 user credentials")
                return creds
        except Exception as e:
            log.warning(f"OAuth2 token invalid: {e} -- falling back to service account")

    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE",
                           str(ROOT / "config" / "google_service_account.json"))
    if not Path(creds_path).exists():
        raise FileNotFoundError(
            f"No OAuth2 token at config/token.json and no service account at {creds_path}.\n"
            "Run: python scripts/setup_oauth.py"
        )
    log.warning("Using service account. Run setup_oauth.py for user credentials.")
    return service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES
    )


def get_or_create_weekly_doc(drive_service, docs_service, folder_id, week_label):
    """Find or create weekly doc. Returns doc_id."""
    doc_name = f"Career Intelligence -- Week of {week_label}"
    query = (
        f"name='{doc_name}' "
        f"and '{folder_id}' in parents "
        f"and mimeType='application/vnd.google-apps.document' "
        f"and trashed=false"
    )
    results = drive_service.files().list(
        q=query, spaces="drive", fields="files(id, name, createdTime)"
    ).execute()
    files = results.get("files", [])
    if files:
        doc_id = files[0]["id"]
        log.info(f"Found existing doc: {doc_name} (id: {doc_id})")
        return doc_id

    file_metadata = {
        "name": doc_name,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id]
    }
    doc = drive_service.files().create(body=file_metadata, fields="id").execute()
    doc_id = doc.get("id")
    log.info(f"Created new doc: {doc_name} (id: {doc_id})")
    return doc_id


def _utf16_len(text):
    """Return number of UTF-16 code units (Google Docs API unit)."""
    return len(text.encode("utf-16-le")) // 2


def append_content_to_doc(docs_service, doc_id, content_text):
    """Append plain text to a Google Doc (used by weekly_rollup.py)."""
    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])
    end_index = content[-1].get("endIndex", 1) - 1 if content else 1

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": content_text}}]}
    ).execute()
    log.info(f"Appended {len(content_text)} characters to doc {doc_id}")


def append_structured_content_to_doc(docs_service, doc_id, blocks):
    """
    Append structured heading blocks to a Google Doc.

    blocks: list of {"text": str, "style": str}
            style: HEADING_1 | HEADING_2 | HEADING_3 | NORMAL_TEXT

    Inserts all text in one request, then applies heading styles via
    updateParagraphStyle with correct UTF-16 code unit positions.
    """
    doc = docs_service.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    insert_at = body_content[-1].get("endIndex", 1) - 1 if body_content else 1

    full_text = ""
    paragraph_ranges = []
    current_offset = 0

    for block in blocks:
        raw_text = block.get("text", "").rstrip("\n")
        style = block.get("style", "NORMAL_TEXT")
        paragraph_text = raw_text + "\n"

        p_start = insert_at + current_offset
        p_len = _utf16_len(paragraph_text)
        p_end = p_start + p_len

        if style != "NORMAL_TEXT":
            paragraph_ranges.append((p_start, p_end, style))

        full_text += paragraph_text
        current_offset += p_len

    if not full_text:
        log.warning("append_structured_content_to_doc: no content to append")
        return

    api_requests = [
        {"insertText": {"location": {"index": insert_at}, "text": full_text}}
    ]
    for start, end, style in paragraph_ranges:
        api_requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": style},
                "fields": "namedStyleType"
            }
        })

    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": api_requests}
    ).execute()

    log.info(
        f"Appended {len(blocks)} blocks ({_utf16_len(full_text)} UTF-16 units) "
        f"with {len(paragraph_ranges)} heading styles to doc {doc_id}"
    )


def get_or_create_daily_doc(drive_service, docs_service, folder_id, day_label):
    """Find or create daily doc. Returns doc_id."""
    doc_name = f"Career Intelligence -- Daily -- {day_label}"
    query = (
        f"name='{doc_name}' "
        f"and '{folder_id}' in parents "
        f"and mimeType='application/vnd.google-apps.document' "
        f"and trashed=false"
    )
    results = drive_service.files().list(
        q=query, spaces="drive", fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    if files:
        doc_id = files[0]["id"]
        log.info(f"Found existing daily doc: {doc_name} (id: {doc_id})")
        return doc_id

    doc = docs_service.documents().create(body={"title": doc_name}).execute()
    doc_id = doc.get("documentId")
    log.info(f"Created new daily doc: {doc_name} (id: {doc_id})")

    drive_service.files().update(
        fileId=doc_id,
        addParents=folder_id,
        removeParents="root",
        fields="id, parents"
    ).execute()
    return doc_id


def write_daily_intelligence(enriched_items, formatted_content, day_label):
    """
    Write daily intelligence to Google Docs.

    formatted_content can be:
      - list of {"text": str, "style": str}  -- structured headings (format_daily_doc)
      - str                                   -- plain text fallback

    Returns (doc_id, doc_url).
    """
    log.info(f"Writing {len(enriched_items)} items to Drive doc: Daily {day_label}")

    try:
        creds = get_google_credentials()
        drive_service = build("drive", "v3", credentials=creds)
        docs_service = build("docs", "v1", credentials=creds)

        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            raise ValueError("GOOGLE_DRIVE_FOLDER_ID not set in .env")

        doc_id = get_or_create_daily_doc(drive_service, docs_service, folder_id, day_label)

        if isinstance(formatted_content, list):
            spacer = [{"text": "", "style": "NORMAL_TEXT"}, {"text": "", "style": "NORMAL_TEXT"}]
            append_structured_content_to_doc(docs_service, doc_id, formatted_content + spacer)
        else:
            append_content_to_doc(docs_service, doc_id, formatted_content + "\n\n")

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        log.info(f"Intelligence written to: {doc_url}")
        return doc_id, doc_url

    except HttpError as e:
        log.error(f"Google API error: {e}")
        raise
    except Exception as e:
        log.error(f"Drive write failed: {e}")
        raise


def write_weekly_intelligence(enriched_items, formatted_content, week_label):
    """Write weekly intelligence doc. Returns (doc_id, doc_url)."""
    log.info(f"Writing {len(enriched_items)} items to Drive doc: Week of {week_label}")

    try:
        creds = get_google_credentials()
        drive_service = build("drive", "v3", credentials=creds)
        docs_service = build("docs", "v1", credentials=creds)

        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            raise ValueError("GOOGLE_DRIVE_FOLDER_ID not set in .env")

        doc_id = get_or_create_weekly_doc(drive_service, docs_service, folder_id, week_label)
        append_content_to_doc(docs_service, doc_id, formatted_content + "\n\n")

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        log.info(f"Intelligence written to: {doc_url}")
        return doc_id, doc_url

    except HttpError as e:
        log.error(f"Google API error: {e}")
        raise
    except Exception as e:
        log.error(f"Drive write failed: {e}")
        raise


def create_content_drafts_folder(drive_service, parent_folder_id, week_label):
    """Create a content-drafts subfolder for the week. Returns folder_id."""
    folder_name = f"Content Drafts -- {week_label}"
    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }
    folder = drive_service.files().create(body=file_metadata, fields="id").execute()
    return folder.get("id")
