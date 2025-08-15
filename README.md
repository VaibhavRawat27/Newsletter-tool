# Flask Newsletter Tool (Gmail OAuth, Quill Editor, Tailwind UI)

A sleek, Gmail-style mini app to manage contacts, compose rich emails, and send them via your own Gmail account using OAuth access tokens.

## Features
- Google OAuth 2.0 to send mail **as you** via Gmail API (no password needed).
- Contacts table: add/edit/delete contacts (name, email, tags, notes).
- Campaigns: compose subject + rich HTML body with **Quill** (bold, images via URL, links).
- Select recipients by multi-select or "All".
- Preview email before sending.
- Sends to single or multiple recipients (as separate messages).
- Modern UI using **Tailwind CSS + DaisyUI**.
- SQLite persistence via **SQLAlchemy**.

## Quickstart
1. **Download** this project and unzip.
2. Create a virtual env and install deps:
   ```bash
   python -m venv .venv
   . .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Create Google OAuth credentials** (Desktop or Web app) at Google Cloud Console.
   - Enable **Gmail API** for your project.
   - Download `credentials.json` and place it in the project root.
4. Copy `.env.example` to `.env` and set `SECRET_KEY` (any random string).
5. Initialize DB and run:
   ```bash
   python app.py
   ```
   App runs at http://127.0.0.1:5000

6. Click **"Connect Gmail"** in the top-right and complete consent. A `token.json` is saved and used for sending.

## Notes
- On first run, SQLite DB is created as `instance/newsletter.db` (or `newsletter.db` in root based on config).
- Each recipient receives an individual message (not CC/BCC) to reduce spam flags.
- You can safely rotate or revoke Google tokens from your Google Account > Security.

## Project Structure
```text
app.py
requirements.txt
.env.example
credentials.json  # (you add this)
token.json        # (auto-created after OAuth)
/templates
  base.html
  index.html
  contacts.html
  campaigns.html
  compose.html
  preview.html
  /partials
    flash.html
    navbar.html
/static
  /css/app.css
  /js/app.js
/instance
  newsletter.db (auto-created)
```

---
**Security Tip:** This demo has no multi-user login. If you deploy it publicly, add auth (e.g., Flask-Login) or IP restrict it.