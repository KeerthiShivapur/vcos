import hashlib
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger("vcos.email")


class EmailService:
    """Phase 1 email transport.

    `console` transport prints the email to the server log and returns it in
    API responses (development mode only). `smtp` transport is ready for
    production configuration via environment variables.
    """

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: Optional[str] = None,
    ) -> dict:
        settings = get_settings()
        if settings.EMAIL_TRANSPORT == "smtp" and settings.SMTP_HOST:
            return await self._send_smtp(to=to, subject=subject, body=body, html=html)
        return await self._send_console(to=to, subject=subject, body=body, html=html)

    async def _send_console(self, *, to: str, subject: str, body: str, html: Optional[str]) -> dict:
        lines = [
            "=" * 72,
            f"TO:      {to}",
            f"SUBJECT: {subject}",
            "=" * 72,
            body,
            "=" * 72,
        ]
        message = "\n".join(lines)
        logger.info("EMAIL\n%s", message)
        return {"transport": "console", "to": to, "subject": subject, "body": body}

    async def _send_smtp(self, *, to: str, subject: str, body: str, html: Optional[str]) -> dict:
        settings = get_settings()
        import aiosmtplib
        from email.message import EmailMessage

        message = EmailMessage()
        message["From"] = settings.SMTP_FROM
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        return {"transport": "smtp", "to": to, "subject": subject}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


email_service = EmailService()
