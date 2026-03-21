import resend
import os

resend.api_key = os.environ['RESEND_API_KEY']

FROM_EMAIL = os.environ.get('FROM_EMAIL', 'briefing@earlyedge.co')
REPLY_TO = os.environ.get('REPLY_TO_EMAIL', FROM_EMAIL)


def send_email(to: str, subject: str, html: str, text: str = None) -> bool:
    try:
        params = {
            "from": f"Early Edge <{FROM_EMAIL}>",
            "to": [to],
            "subject": subject,
            "html": html,
            "reply_to": REPLY_TO,
        }
        if text:
            params["text"] = text
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"[email] Failed to send to {to}: {e}")
        return False
