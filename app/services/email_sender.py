# app/services/email_sender.py
#
# EmailSender: delivers the digest email via Gmail SMTP + App Password.
#
# Encoding note (important):
# We force base64 body encoding instead of Python's default quoted-printable
# for utf-8 emails. Quoted-printable inserts a soft line break every ~76
# characters with no awareness of HTML structure — if that break lands
# inside an <img src="..."> URL, the URL gets corrupted (this caused the
# "broken icon, no real link" bug). Base64 has no line-length concept, so
# URLs can never be split mid-string.

from __future__ import annotations

import logging
import smtplib
import ssl
from email.charset import BASE64, Charset
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_UTF8_BASE64 = Charset("utf-8")
_UTF8_BASE64.body_encoding = BASE64


class EmailSender:
    """
    Sends an AI digest email via Gmail SMTP.

    Credentials are read from environment variables:
        GMAIL_ADDRESS       — sender address
        GMAIL_APP_PASSWORD  — Google App Password (16 chars, no spaces)

    If either variable is missing, send() logs a warning and returns False
    without raising, so the pipeline doesn't crash on a missing credential.
    """

    _SMTP_HOST = "smtp.gmail.com"
    _SMTP_PORT = 465  # SSL

    def __init__(self) -> None:
        import os
        self._address = os.getenv("GMAIL_ADDRESS", "")
        self._password = os.getenv("GMAIL_APP_PASSWORD", "")

    @property
    def is_configured(self) -> bool:
        return bool(self._address and self._password)

    def send(
        self,
        *,
        to_address: str,
        subject: str,
        body_html: str,
        body_text: str,
    ) -> bool:
        """
        Send an email.

        Parameters
        ----------
        to_address : recipient email address
        subject    : email subject line
        body_html  : the Medium-style HTML body (from email_template.render_email_html)
        body_text  : plain-text fallback (from EmailDigestResponse.to_markdown())
        """
        if not self.is_configured:
            logger.warning(
                "EmailSender: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set — "
                "email not sent. Set these in your .env file."
            )
            return False

        msg = self._build_message(
            from_address=self._address,
            to_address=to_address,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
        )

        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self._SMTP_HOST, self._SMTP_PORT, context=ctx) as server:
                server.login(self._address, self._password)
                raw = msg.as_string()
                with open("debug_actual_sent_mime.eml", "w", encoding="utf-8") as f:
                    f.write(raw)
                server.sendmail(self._address, to_address, msg.as_string())
            logger.info("EmailSender: digest sent to %s", to_address)
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error(
                "EmailSender: Gmail authentication failed. "
                "Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD."
            )
        except smtplib.SMTPException as exc:
            logger.error("EmailSender: SMTP error — %s", exc)
        except OSError as exc:
            logger.error("EmailSender: network error — %s", exc)
        return False

    @staticmethod
    def _build_message(
        *,
        from_address: str,
        to_address: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = to_address

        # RFC order matters: plain FIRST, html LAST — clients render the
        # last part they understand, so html (with images) wins.
        plain_fallback = body_text or "This email requires an HTML-capable client to view."
        msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        return msg