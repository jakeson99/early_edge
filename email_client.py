import resend
import os

resend.api_key = os.environ['RESEND_API_KEY']

FROM_EMAIL = os.environ.get('FROM_EMAIL', 'briefing@earlyedge.co')


def send_email(to: str, subject: str, html: str) -> bool:
    try:
        resend.Emails.send({
            "from": f"Early Edge <{FROM_EMAIL}>",
            "to": [to],
            "subject": subject,
            "html": html,
        })
        return True
    except Exception as e:
        print(f"[email] Failed to send to {to}: {e}")
        return False
