# app/services/email_sender.py
#
# EmailSender: delivers the digest email via Gmail SMTP + App Password.
#
# Images are embedded directly in the email as inline (Content-ID) parts
# instead of linked as remote <img src="https://..."> URLs. This guarantees
# they render in every email client regardless of the client's own image
# proxy, "display external images" setting, or sender-trust heuristics.

from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_IMG_SRC_RE = re.compile(r'<img[^>]+src="(https?://[^"]+)"', re.IGNORECASE)


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
    _IMAGE_FETCH_TIMEOUT = 8  # seconds, per image

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
        to_address : recipient email address
        subject    : email subject line
        body_html  : the rendered HTML digest (from email_template.render_email_html)
        body_text  : plain-text fallback (from EmailDigestResponse.to_markdown())

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
        """
        multipart/alternative
          |-- text/plain                         (fallback)
          `-- multipart/related                  (only if images were inlined)
                |-- text/html                    (references cid:img0, cid:img1, ...)
                |-- image/jpeg  Content-ID: <img0>
                `-- image/jpeg  Content-ID: <img1>
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = to_address

        plain_fallback = body_text or "This email requires an HTML-capable client to view."
        msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))

        inlined_html, image_parts = _inline_images(body_html)

        if image_parts:
            related = MIMEMultipart("related")
            related.attach(MIMEText(inlined_html, "html", "utf-8"))
            for img in image_parts:
                related.attach(img)
            msg.attach(related)
        else:
            # No images fetched successfully (or none present) — send html as-is.
            msg.attach(MIMEText(inlined_html, "html", "utf-8"))

        return msg


# ---------------------------------------------------------------------------
# Image inlining — converts remote <img src="https://..."> into embedded
# Content-ID attachments so rendering never depends on the recipient's
# email client fetching a remote URL.
# ---------------------------------------------------------------------------

def _fetch_image_bytes(url: str, timeout: int) -> Tuple[Optional[bytes], Optional[str]]:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        subtype = content_type.split("/")[-1].split(";")[0].strip() or "jpeg"
        return resp.content, subtype
    except Exception as exc:
        logger.warning("EmailSender: failed to fetch image %s — %s", url, exc)
        return None, None


def _inline_images(html: str) -> Tuple[str, List[MIMEImage]]:
    """
    Replace every remote <img src="https://..."> in `html` with a cid:
    reference, returning the rewritten html plus the MIMEImage parts to
    attach. If a specific image fails to download, that one <img> tag is
    left pointing at its original remote URL (graceful degradation) rather
    than breaking the whole send.
    """
    parts: List[MIMEImage] = []

    def _replace(match: "re.Match[str]") -> str:
        url = match.group(1)
        data, subtype = _fetch_image_bytes(url, EmailSender._IMAGE_FETCH_TIMEOUT)
        if data is None:
            return match.group(0)
        cid = f"img{len(parts)}"
        img = MIMEImage(data, _subtype=subtype)
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.{subtype}")
        parts.append(img)
        return match.group(0).replace(url, f"cid:{cid}")

    new_html = _IMG_SRC_RE.sub(_replace, html)
    return new_html, parts