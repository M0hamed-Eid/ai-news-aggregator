# app/services/__init__.py
from app.services.digest_service import DigestService, DigestServiceResult
from app.services.email_sender import EmailSender

__all__ = [
    "DigestService",
    "DigestServiceResult",
    "EmailSender",
]