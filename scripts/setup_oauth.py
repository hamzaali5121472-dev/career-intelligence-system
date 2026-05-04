#!/usr/bin/env python3
"""
One-time OAuth2 setup — run this once to authorize Drive access as yourself.
Your files will then count against YOUR Google quota (not the service account).

Usage:
    python scripts/setup_oauth.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "config"
TOKEN_FILE = CONFIG / "token.json"
CLIENT_SECRETS = CONFIG / "client_secrets.json"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents"
]

def main():
    if not CLIENT_SECRETS.exists():
        print()
        print("ERROR: config/client_secrets.json not found")
        print()
        print("Steps to get it:")
        print("1. Go to: https://console.cloud.google.com")
        print("2. Make sure project \'B2Have Career Intel\' is selected")
        print("3. Click: APIs & Services -> Credentials")
        print("4. Click: + Create Credentials -> OAuth client ID")
        print("5. Application type: Desktop app")
        print("6. Name: b2have-career-intel")
        print("7. Click Create -> Download JSON")
        print("8. Save the downloaded file as: config/client_secrets.json")
        print()
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installing google-auth-oauthlib...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install",
                       "google-auth-oauthlib", "--break-system-packages"],
                      capture_output=True)
        from google_auth_oauthlib.flow import InstalledAppFlow

    print("Opening browser for Google authorization...")
    print("Sign in as hamzaali5121472@gmail.com and click Allow.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print()
    print(f"Success! Token saved to: {TOKEN_FILE}")
    print("Google Drive will now create files as YOUR account.")
    print("Your 5TB quota will be used — no more quota errors.")

if __name__ == "__main__":
    main()
