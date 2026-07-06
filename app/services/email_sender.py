# app/services/email_sender.py
#
# EmailSender: delivers the digest email via Gmail SMTP + App Password.
#
# Why this service exists
# -----------------------
# The uploaded project had an empty email_sender.py.  The .env.example already
# defines GMAIL_ADDRESS and GMAIL_APP_PASSWORD, so the infrastructure is ready;
# it just needs an implementation.
#
# Design notes
# ------------
# - Uses Python's built-in smtplib + ssl — no extra dependencies.
# - Sends both a plain-text (Markdown) part and an HTML part so most email
#   clients render something useful.
# - HTML is the Markdown body wrapped in a minimal responsive template.
# - Falls back gracefully when credentials are missing (log warning, no crash).

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


class EmailSender:
    """
    Sends an AI digest email via Gmail SMTP.

    Credentials are read from environment variables:
        GMAIL_ADDRESS       — sender address
        GMAIL_APP_PASSWORD  — Google App Password (16 chars, no spaces)

    If either variable is missing the send() method logs a warning and
    returns False without raising, so the pipeline doesn't crash on a
    missing credential.
    """

    _SMTP_HOST = "smtp.gmail.com"
    _SMTP_PORT = 465  # SSL

    def __init__(self) -> None:
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
        body_text: Optional[str] = None,
    ) -> bool:
        """
        Send an email.

        Parameters
        ----------
        to_address    : recipient email address
        subject       : email subject line
        body_markdown : plain-text / Markdown body (also used for the HTML part)

        Returns True on success, False on failure.
        """
        if not self.is_configured:
            logger.warning(
                "EmailSender: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set — "
                "email not sent.  Set these in your .env file."
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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

        # Plain-text part (fallback for text-only clients)
        msg.attach(MIMEText(body_markdown, "plain", "utf-8"))

        # Minimal HTML wrapper
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        return msg


# ---------------------------------------------------------------------------
# Minimal Markdown → HTML converter (no extra deps)
# ---------------------------------------------------------------------------

# def _markdown_to_html(md: str) -> str:
#     """
#     Very lightweight Markdown → HTML conversion for digest emails.

#     Handles: h2 headings, horizontal rules, bold links, paragraphs.
#     For a richer renderer add `markdown` or `mistune` to pyproject.toml
#     and replace this function.
#     """
#     import html as html_lib
#     import re

#     lines = md.split("\n")
#     html_lines: list[str] = [
#         "<html><body style='font-family:sans-serif;max-width:680px;margin:auto;padding:16px;'>"
#     ]

#     for line in lines:
#         stripped = line.strip()

#         if stripped.startswith("## "):
#             text = html_lib.escape(stripped[3:])
#             html_lines.append(f"<h2 style='color:#1a1a1a;'>{text}</h2>")

#         elif stripped == "---":
#             html_lines.append("<hr style='border:none;border-top:1px solid #ddd;margin:16px 0;'>")

#         elif re.match(r"^\[.+\]\(.+\)$", stripped):
#             # Bare link line: [label](url)
#             m = re.match(r"^\[(.+)\]\((.+)\)$", stripped)
#             if m:
#                 label = html_lib.escape(m.group(1))
#                 url = html_lib.escape(m.group(2))
#                 html_lines.append(
#                     f"<p><a href='{url}' style='color:#0066cc;'>{label}</a></p>"
#                 )

#         elif stripped == "":
#             html_lines.append("")  # keep spacing

#         else:
#             text = html_lib.escape(stripped)
#             html_lines.append(f"<p style='color:#333;line-height:1.6;'>{text}</p>")

#     html_lines.append("</body></html>")
#     return "\n".join(html_lines)