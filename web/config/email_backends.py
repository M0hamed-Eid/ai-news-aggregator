# web/config/email_backends.py
#
# Resend HTTP API email backend. Django's SMTP backend can't reach
# smtp.gmail.com from Render at all -- confirmed live (2026-08-09):
# OSError: [Errno 101] Network is unreachable, connecting to
# smtp.gmail.com:465. Render blocks/has no route for outbound raw SMTP;
# Resend sends over plain HTTPS instead, which obviously works since the
# whole app already runs over HTTPS. A small custom backend (not
# django-anymail, which supports ~15 providers we don't need for one)
# implementing Django's BaseEmailBackend interface, so every existing
# send_mail()/EmailMultiAlternatives call (verification emails, password
# reset, digest test sends) works completely unchanged -- only
# settings.EMAIL_BACKEND's dotted path changes, see base.py.
import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            html_body = None
            for alt_content, alt_mimetype in getattr(message, "alternatives", []):
                if alt_mimetype == "text/html":
                    html_body = alt_content
                    break

            payload = {
                "from": message.from_email,
                "to": list(message.to),
                "subject": message.subject,
                "text": message.body,
            }
            if html_body:
                payload["html"] = html_body

            try:
                response = requests.post(
                    RESEND_API_URL,
                    headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
                sent += 1
            except requests.RequestException:
                logger.warning("ResendEmailBackend: send failed for subject=%r", message.subject, exc_info=True)
                if not self.fail_silently:
                    raise
        return sent
