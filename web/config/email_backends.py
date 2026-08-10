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
#
# GmailAPIEmailBackend below is the same idea over a different provider:
# found live during the 2026-08-10 QA pass that Resend's sandbox mode
# (no verified domain, and the user declined to buy one) only delivers to
# the account owner's own exact address -- every OTHER real signup gets no
# verification/reset email at all. The Gmail API sends over HTTPS too (so
# it's equally unaffected by Render's SMTP block) but, once OAuth-
# authorized, an ordinary Gmail account can send to any recipient with no
# domain-verification step -- the trade is a one-time OAuth consent flow
# instead (see scripts/get_gmail_refresh_token.py) rather than DNS records.
import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


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


class GmailAPIEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        access_token = self._get_access_token()
        if access_token is None:
            if not self.fail_silently:
                raise RuntimeError("GmailAPIEmailBackend: couldn't refresh a Gmail API access token")
            return 0

        sent = 0
        for message in email_messages:
            try:
                raw = self._build_raw_message(message)
                response = requests.post(
                    GMAIL_SEND_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"raw": raw},
                    timeout=10,
                )
                response.raise_for_status()
                sent += 1
            except requests.RequestException:
                logger.warning("GmailAPIEmailBackend: send failed for subject=%r", message.subject, exc_info=True)
                if not self.fail_silently:
                    raise
        return sent

    @staticmethod
    def _get_access_token():
        try:
            response = requests.post(
                GMAIL_TOKEN_URL,
                data={
                    "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
                    "client_secret": settings.GMAIL_OAUTH_CLIENT_SECRET,
                    "refresh_token": settings.GMAIL_OAUTH_REFRESH_TOKEN,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()["access_token"]
        except requests.RequestException:
            logger.warning("GmailAPIEmailBackend: access token refresh failed", exc_info=True)
            return None

    @staticmethod
    def _build_raw_message(message):
        html_body = None
        for alt_content, alt_mimetype in getattr(message, "alternatives", []):
            if alt_mimetype == "text/html":
                html_body = alt_content
                break

        if html_body:
            mime_message = MIMEMultipart("alternative")
            mime_message.attach(MIMEText(message.body, "plain"))
            mime_message.attach(MIMEText(html_body, "html"))
        else:
            mime_message = MIMEText(message.body, "plain")

        mime_message["To"] = ", ".join(message.to)
        mime_message["From"] = message.from_email
        mime_message["Subject"] = message.subject

        # Gmail API wants the raw RFC 2822 message, base64url-encoded.
        return base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
