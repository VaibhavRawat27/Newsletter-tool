import os, json, pathlib, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from dotenv import load_dotenv

# Google API libs
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from email.mime.text import MIMEText
from email.utils import formataddr

load_dotenv()

app = Flask(__name__, instance_relative_config=True)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
db_url = os.getenv("DATABASE_URL", "sqlite:///newsletter.db")
# if relative path, put DB in instance/
if db_url.startswith("sqlite:///") and not os.path.isabs(db_url.replace("sqlite:///", "")):
    db_path = os.path.join(app.instance_path, db_url.replace("sqlite:///", ""))
    os.makedirs(app.instance_path, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------- Models ----------
class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    tags = db.Column(db.String(255))
    notes = db.Column(db.String(500))

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(255), nullable=False)
    from_name = db.Column(db.String(120))
    html_body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    status = db.Column(db.String(50), default="draft")
    recipients = relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")

class CampaignRecipient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaign.id"))
    email = db.Column(db.String(255), nullable=False)
    campaign = relationship("Campaign", back_populates="recipients")

with app.app_context():
    db.create_all()

# ---------- Gmail OAuth helpers ----------
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

def gmail_credentials():
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        return creds
    return None

def gmail_connected():
    creds = gmail_credentials()
    return bool(creds and creds.valid)

@app.route("/auth/google")
def connect_gmail():
    if not os.path.exists(CREDS_FILE):
        flash("credentials.json not found in project root. Please add your Google OAuth client.", "error")
        return redirect(url_for("index"))
    flow = Flow.from_client_secrets_file(
        CREDS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True),
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["state"] = state
    return redirect(auth_url)

@app.route("/auth/callback")
def oauth2callback():
    state = session.get("state")
    flow = Flow.from_client_secrets_file(
        CREDS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True),
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    flash("Gmail connected successfully.", "success")
    return redirect(url_for("index"))

@app.route("/auth/disconnect")
def disconnect_gmail():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    flash("Disconnected Gmail.", "info")
    return redirect(url_for("index"))

# ---------- Utility: send via Gmail API ----------
def send_email_via_gmail(to_email, subject, html_body, from_name=None):
    creds = gmail_credentials()
    if not creds:
        raise RuntimeError("Gmail is not connected. Connect via 'Connect Gmail' button.")

    try:
        service = build("gmail", "v1", credentials=creds)
        sender = "me"
        if from_name:
            from_header = formataddr((from_name, ""))  # Gmail fills sender
        else:
            from_header = None

        msg = MIMEText(html_body, "html")
        msg["To"] = to_email
        msg["Subject"] = subject
        if from_header:
            msg["From"] = from_header

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        body = {"raw": raw}
        sent = service.users().messages().send(userId=sender, body=body).execute()
        return sent.get("id")
    except HttpError as e:
        raise RuntimeError(f"Gmail API error: {e}")

# ---------- Routes ----------
@app.context_processor
def inject_globals():
    return {"gmail_connected": gmail_connected()}

@app.route("/")
def index():
    return render_template("index.html", title="Dashboard")

# Contacts
@app.route("/contacts")
def contacts():
    contacts = Contact.query.order_by(Contact.id.desc()).all()
    return render_template("contacts.html", contacts=contacts, title="Contacts")

@app.route("/contacts/add", methods=["POST"])
def add_contact():
    name = request.form.get("name")
    email = request.form.get("email")
    tags = request.form.get("tags")
    notes = request.form.get("notes")
    if not name or not email:
        flash("Name and email are required.", "error")
        return redirect(url_for("contacts"))
    if Contact.query.filter_by(email=email).first():
        flash("Email already exists in contacts.", "warning")
        return redirect(url_for("contacts"))
    c = Contact(name=name, email=email, tags=tags, notes=notes)
    db.session.add(c)
    db.session.commit()
    flash("Contact added.", "success")
    return redirect(url_for("contacts"))

@app.route("/contacts/<int:contact_id>/delete", methods=["POST"])
def delete_contact(contact_id):
    c = Contact.query.get_or_404(contact_id)
    db.session.delete(c)
    db.session.commit()
    flash("Contact deleted.", "info")
    return redirect(url_for("contacts"))

# Campaigns list
@app.route("/campaigns")
def campaigns():
    camps = Campaign.query.order_by(Campaign.created_at.desc()).all()
    return render_template("campaigns.html", campaigns=camps, title="Campaigns")

# Compose new / duplicate existing
@app.route("/compose", methods=["GET", "POST"])
def compose():
    if request.method == "POST":
        subject = request.form.get("subject")
        from_name = request.form.get("from_name") or None
        html_body = request.form.get("html_body") or ""
        if not subject or not html_body.strip():
            flash("Subject and body are required.", "error")
            return redirect(url_for("compose"))
        camp = Campaign(subject=subject, from_name=from_name, html_body=html_body, status="draft")
        db.session.add(camp)
        db.session.commit()
        flash("Draft saved.", "success")
        return redirect(url_for("campaigns"))
    # GET
    duplicate_id = request.args.get("duplicate_id", type=int)
    subject = from_name = html_body = None
    if duplicate_id:
        orig = Campaign.query.get_or_404(duplicate_id)
        subject = orig.subject
        from_name = orig.from_name
        html_body = orig.html_body
    contacts = Contact.query.order_by(Contact.name.asc()).all()
    return render_template("compose.html", contacts=contacts, subject=subject, from_name=from_name, html_body=html_body, title="Compose")

# Preview current unsaved form (post)
@app.route("/preview", methods=["POST"])
def preview_current():
    subject = request.form.get("subject")
    html_body = request.form.get("html_body")
    from_name = request.form.get("from_name") or None
    recipient_ids = request.form.getlist("recipient_ids")
    one_off = request.form.get("one_off_email")
    recips = []
    for rid in recipient_ids:
        c = Contact.query.get(int(rid))
        if c: recips.append(f"{c.name} <{c.email}>")
    if one_off:
        recips.append(one_off)
    return render_template("preview.html", subject=subject, html_body=html_body, recipients=recips, recipient_ids=recipient_ids, one_off_email=one_off, title="Preview")

# Preview saved campaign by id
@app.route("/campaigns/<int:campaign_id>/preview")
def preview_campaign(campaign_id):
    camp = Campaign.query.get_or_404(campaign_id)
    recips = [r.email for r in camp.recipients]
    return render_template("preview.html", subject=camp.subject, html_body=camp.html_body, recipients=recips, recipient_ids=[], one_off_email=None, title="Preview")

# Send now (from compose or preview)
@app.route("/send", methods=["POST"])
def send_now():
    subject = request.form.get("subject")
    html_body = request.form.get("html_body")
    from_name = request.form.get("from_name") or None
    recipient_ids = request.form.getlist("recipient_ids")
    one_off = request.form.get("one_off_email")

    # Collect emails
    emails = []
    for rid in recipient_ids:
        c = Contact.query.get(int(rid))
        if c and c.email not in emails:
            emails.append(c.email)
    if one_off:
        emails.append(one_off)

    if not emails:
        flash("No recipients selected.", "warning")
        return redirect(url_for("compose"))

    # Persist campaign
    camp = Campaign(subject=subject, from_name=from_name, html_body=html_body, status="queued")
    db.session.add(camp)
    db.session.flush()
    for em in emails:
        db.session.add(CampaignRecipient(campaign=camp, email=em))
    db.session.commit()

    # Send per-recipient
    sent_count = 0
    try:
        for em in emails:
            send_email_via_gmail(em, subject, html_body, from_name=from_name)
            sent_count += 1
        camp.status = "sent"
        db.session.commit()
        flash(f"Sent {sent_count} message(s).", "success")
    except Exception as e:
        camp.status = f"error: {e}"
        db.session.commit()
        flash(f"Error while sending: {e}", "error")

    return redirect(url_for("campaigns"))

# Convenience routes
@app.route("/connect")
def connect_redirect():
    return redirect(url_for("connect_gmail"))

if __name__ == "__main__":
    app.run(debug=True)
