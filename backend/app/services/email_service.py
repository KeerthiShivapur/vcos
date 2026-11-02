import hashlib
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger("vcos.email")


class EmailService:
    """Phase 1 email transport.

    `console` transport logs the email body (development only) and returns it
    in API responses. In production the console transport never logs or
    returns the body and is treated as not-delivered. `smtp` transport is the
    production path: STARTTLS on 587-style ports, implicit TLS on 465, with
    bounded retries. Credentials are never logged.
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
        settings = get_settings()
        if settings.APP_ENV == "production":
            logger.warning(
                "EMAIL (console transport in production; body suppressed) to=%s subject=%s",
                to, subject,
            )
            return {
                "transport": "console",
                "to": to,
                "subject": subject,
                "delivered": False,
                "note": "console transport in production never delivers mail",
            }
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
        return {"transport": "console", "to": to, "subject": subject, "body": body, "delivered": True}

    async def _send_smtp(self, *, to: str, subject: str, body: str, html: Optional[str]) -> dict:
        settings = get_settings()
        import asyncio

        import aiosmtplib
        from email.message import EmailMessage

        message = EmailMessage()
        message["From"] = settings.SMTP_FROM
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")

        # port 465 = implicit TLS; other ports = STARTTLS upgrade
        implicit_tls = settings.SMTP_PORT == 465
        attempts = 3
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                await aiosmtplib.send(
                    message,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USER,
                    password=settings.SMTP_PASSWORD,
                    start_tls=not implicit_tls,
                    use_tls=implicit_tls,
                    timeout=30,
                )
                return {"transport": "smtp", "to": to, "subject": subject, "delivered": True}
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "SMTP delivery attempt %s/%s failed: %s", attempt, attempts, type(exc).__name__,
                )
                if attempt < attempts:
                    await asyncio.sleep(2 * attempt)
        logger.error("SMTP delivery failed after %s attempts (host=%s)", attempts, settings.SMTP_HOST)
        raise RuntimeError(f"SMTP delivery failed: {type(last_error).__name__}") from last_error


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


email_service = EmailService()
