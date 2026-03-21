from datetime import date
from jinja2 import Environment, FileSystemLoader
import db
import claude_client
import email_client

_template_env = Environment(loader=FileSystemLoader('templates'))


def send_briefing(user: dict):
    today = date.today()
    local_date = today.isoformat()

    if db.has_sent_today(user['id'], local_date):
        print(f"[job] Already sent to {user['email']} today — skipping.")
        return

    print(f"[job] Generating briefing for {user['name']} ({user['email']})…")

    try:
        briefing = claude_client.generate_briefing(user, today)
    except Exception as e:
        print(f"[job] Claude error for {user['email']}: {e}")
        return

    try:
        template = _template_env.get_template('email.html')
        html = template.render(
            user=user,
            briefing=briefing,
            date_str=today.strftime('%A, %d %B %Y'),
        )
    except Exception as e:
        print(f"[job] Template error for {user['email']}: {e}")
        return

    subject = f"Your Early Edge — {today.strftime('%a %d %b')}"
    success = email_client.send_email(user['email'], subject, html)

    if success:
        db.record_send(user['id'], local_date)
        print(f"[job] ✓ Sent to {user['email']}")
    else:
        print(f"[job] ✗ Failed to send to {user['email']}")
