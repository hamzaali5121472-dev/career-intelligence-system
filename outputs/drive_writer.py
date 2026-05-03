"""
Google Drive Writer — B2Have Career Intelligence System
Authenticates via service account, writes enriched intelligence to Google Docs.

Creates structured weekly documents in a designated Drive folder.
NotebookLM syncs from this folder — this is the bridge between the bot and NLM.

Auth: Service Account JSON (never requires manual login)
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2 import service_account
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
    """Load service account credentials from JSON file."""
    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE",
                           str(ROOT / "config" / "google_service_account.json"))

    if not Path(creds_path).exists():
        raise FileNotFoundError(
            f"Google service account JSON not found at: {creds_path}\n"
            "Download it from Google Cloud Console → IAM → Service Accounts → Keys"
        )

    return service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES
    )


def get_or_create_weekly_doc(drive_service, docs_service, folder_id, week_label):
    """
    Find existing week doc or create a new one.
    Doc naming convention: "Career Intelligence — Week of YYYY-MM-DD"
    Returns doc_id.
    """
    doc_name = f"Career Intelligence — Week of {week_label}"

    # Search for existing doc in folder
    query = (
        f"name='{doc_name}' "
        f"and '{folder_id}' in parents "
        f"and mimeType='application/vnd.google-apps.document' "
        f"and trashed=false"
    )

    results = drive_service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, createdTime)"
    ).execute()

    files = results.get("files", [])

    if files:
        doc_id = files[0]["id"]
        log.info(f"Found existing doc: {doc_name} (id: {doc_id})")
        return doc_id

    # Create new doc
    file_metadata = {
        "name": doc_name,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id]
    }

    doc = drive_service.files().create(
        body=file_metadata,
        fields="id"
    ).execute()

    doc_id = doc.get("id")
    log.info(f"Created new doc: {doc_name} (id: {doc_id})")

    return doc_id


def append_content_to_doc(docs_service, doc_id, content_text):
    """
    Append text content to a Google Doc.
    Uses batchUpdate to insert text at end of document.
    """
    # First, get current doc length to insert at end
    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])
    end_index = content[-1].get("endIndex", 1) - 1 if content else 1

    requests = [
        {
            "insertText": {
                "location": {"index": end_index},
                "text": content_text
            }
        }
    ]

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests}
    ).execute()

    log.info(f"Appended {len(content_text)} characters to doc {doc_id}")


def write_weekly_intelligence(enriched_items, formatted_content, week_label):
    """
    Main function: write formatted intelligence to Google Docs.
    Creates/finds the weekly doc and appends content.
    Returns the doc URL.
    """
    log.info(f"Writing {len(enriched_items)} items to Drive doc: Week of {week_label}")

    try:
        creds = get_google_credentials()
        drive_service = build("drive", "v3", credentials=creds)
        docs_service = build("docs", "v1", credentials=creds)

        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            raise ValueError(
                "GOOGLE_DRIVE_FOLDER_ID not set in .env\n"
                "Create a folder in Google Drive, share it with your service account email, "
                "then copy its ID from the URL."
            )

        doc_id = get_or_create_weekly_doc(drive_service, docs_service, folder_id, week_label)

        # Append the formatted content
        append_content_to_doc(docs_service, doc_id, formatted_content + "\n\n")

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        log.info(f"✓ Intelligence written to: {doc_url}")

        return doc_id, doc_url

    except HttpError as e:
        log.error(f"Google API error: {e}")
        raise
    except Exception as e:
        log.error(f"Drive write failed: {e}")
        raise


def create_content_drafts_folder(drive_service, parent_folder_id, week_label):
    """
    Create a content-drafts subfolder for the week.
    Returns folder_id.
    """
    folder_name = f"Content Drafts — {week_label}"

    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id]
    }

    folder = drive_service.files().create(
        body=file_metadata,
        fields="id"
    ).execute()

    return folder.get("id")
