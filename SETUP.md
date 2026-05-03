# B2Have Career Intelligence System — Setup Guide

## Your First 5 Days — Exact Steps

---

## DAY 1 — Environment Setup (2-3 hours)

### 1. Install Prerequisites
- Python 3.11+: https://python.org/downloads
- Git: https://git-scm.com/downloads
- VS Code: https://code.visualstudio.com

### 2. Set Up the Project
Open VS Code, open a terminal (Ctrl+`), then:

```bash
# Navigate to where you want the project
cd C:\Users\Inspiron\Documents

# Initialize git
cd career-intelligence-system
git init
git add .
git commit -m "Initial commit — B2Have Career Intelligence System"

# Create Python virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate   # Mac/Linux

# Install all dependencies
pip install -r requirements.txt

# Create your .env file from template
copy .env.example .env
```

### 3. Verify Installation
```bash
python -c "import praw, anthropic, feedparser; print('All packages installed OK')"
```

---

## DAY 2 — API Keys (2 hours)

### Reddit Developer App
1. Go to: https://www.reddit.com/prefs/apps
2. Click "Create another app"
3. Name: `b2have_career_intel`
4. Type: **script**
5. Description: Career coaching market intelligence
6. Redirect URI: `http://localhost:8080`
7. Click "create app"
8. Copy: `client_id` (under app name), `secret`
9. Add to `.env`:
   ```
   REDDIT_CLIENT_ID=the_id_under_app_name
   REDDIT_CLIENT_SECRET=the_secret_value
   REDDIT_USER_AGENT=b2have_career_intel/1.0 by /u/YOUR_USERNAME
   REDDIT_USERNAME=YOUR_REDDIT_USERNAME
   REDDIT_PASSWORD=YOUR_REDDIT_PASSWORD
   ```

### Anthropic API Key
1. Go to: https://console.anthropic.com
2. Sign up / log in
3. Click "API Keys" → "Create Key"
4. Name it: `b2have_career_intel`
5. IMPORTANT: Go to "Billing" → set a monthly spend limit of $15 CAD
6. Add to `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-your_key_here
   ```

### Google Cloud + Drive API
1. Go to: https://console.cloud.google.com
2. Create new project: "B2Have Career Intel"
3. Enable APIs (search and enable each):
   - "Google Drive API"
   - "Google Docs API"
4. Go to "IAM & Admin" → "Service Accounts"
5. Click "Create Service Account"
   - Name: `career-intel-bot`
   - Click "Create and Continue"
   - Role: "Editor"
   - Click "Done"
6. Click the service account → "Keys" tab → "Add Key" → "JSON"
7. Download the JSON file → save as `config/google_service_account.json`
8. **IMPORTANT**: The JSON file contains an email like `career-intel-bot@....iam.gserviceaccount.com`
   Copy that email address — you'll need it in the next step.

### Google Drive Folder Setup
1. Go to: https://drive.google.com
2. Create a new folder: "B2Have Career Intelligence"
3. Inside it, create: "Weekly Intelligence Docs"
4. Right-click "Weekly Intelligence Docs" → Share
5. Paste the service account email (from step 8 above)
6. Set permission to "Editor" → Share
7. Click the folder → look at the URL: `https://drive.google.com/drive/folders/FOLDER_ID_HERE`
8. Copy the folder ID
9. Add to `.env`:
   ```
   GOOGLE_DRIVE_FOLDER_ID=the_folder_id_from_url
   ```

### Gmail Alert Setup (Optional but Recommended)
1. Go to your Google Account → Security → 2-Step Verification (enable if not done)
2. Go to: https://myaccount.google.com/apppasswords
3. Select app: "Mail", device: "Windows Computer"
4. Copy the 16-character password
5. Add to `.env`:
   ```
   ALERT_EMAIL_FROM=your_gmail@gmail.com
   ALERT_EMAIL_TO=hamzaali5121472@gmail.com
   ALERT_EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```

---

## DAY 3 — Test Reddit Collector (1-2 hours)

```bash
# Activate venv if not already active
venv\Scripts\activate

# Test your connections first
python main.py --test

# If all 3 show ✓, run Reddit collection
python -m collectors.reddit_collector

# Check the output
dir data\raw\
# You should see: reddit_YYYYMMDD_HHMMSS.json
```

Open that JSON file in VS Code — you should see 50-100+ posts with full text.

---

## DAY 4 — Test AI Enrichment (1 hour)

```bash
# Run enrichment on yesterday's collected data
python -m enrichment.claude_enricher

# Check the output
dir data\enriched\
# You should see: enriched_YYYYMMDD_HHMMSS.json
```

Open the enriched file — each post now has `theme`, `relevance_score`, `power_quote`, 
`audience_segment`, `coaching_flag`.

---

## DAY 5 — Write to Drive + NotebookLM (2 hours)

```bash
# Write enriched data to Google Drive
python main.py --skip-reddit --skip-rss

# This will create a Google Doc in your Drive folder
# Check the console output for the doc URL
```

### Set Up NotebookLM
1. Go to: https://notebooklm.google.com
2. Create 4 notebooks:
   - "Live Pulse — Current Week"
   - "Trend Archive — Last 6 Months"
   - "Knowledge Base — Evergreen Research"
   - "Competitor Intel"
3. In "Live Pulse":
   - Click "+ Add Source"
   - Choose "Google Drive"
   - Connect your Google account
   - Select the "Weekly Intelligence Docs" folder
   - Click "Add"
4. Ask your first question:
   `"What career themes are most discussed this week in Canada?"`

---

## GitHub Actions Setup (After Day 5)

1. Push the project to GitHub:
   ```bash
   # Create repo at github.com/new
   # Then:
   git remote add origin https://github.com/YOUR_USERNAME/career-intelligence-system.git
   git push -u origin main
   ```

2. Add secrets in GitHub (Settings → Secrets and variables → Actions → New secret):
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`
   - `REDDIT_USER_AGENT`
   - `REDDIT_USERNAME`
   - `REDDIT_PASSWORD`
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_CREDS_JSON` — paste the entire contents of `config/google_service_account.json`
   - `GOOGLE_DRIVE_FOLDER_ID`
   - `ALERT_EMAIL_FROM`
   - `ALERT_EMAIL_TO`
   - `ALERT_EMAIL_APP_PASSWORD`

3. The workflows will start running automatically on their schedules.
   You can also trigger them manually from the Actions tab.

---

## Weekly Usage — What You Do Every Week

**Monday morning (5 minutes):**
1. Open NotebookLM "Live Pulse" notebook
2. Click "Sync" to refresh with latest Drive docs
3. Ask: "What are the top 5 career themes this week?"
4. Ask: "Give me 3 power quotes I can use in LinkedIn content"
5. Ask: "What coaching opportunities surfaced this week?"

**That's it.** The system runs everything else automatically.

---

## Troubleshooting

**"REDDIT_CLIENT_ID not set"** — Check `.env` file, make sure it's in the project root

**"Google service account JSON not found"** — Download from Google Cloud Console → 
save exactly as `config/google_service_account.json`

**"GOOGLE_DRIVE_FOLDER_ID not set"** — Get it from the Drive folder URL

**"No enriched items to write"** — Run collection first, wait, then run enrichment

**Reddit returns 0 posts** — Check that your Reddit app type is "script" and credentials are correct

For help: hamzaali5121472@gmail.com
