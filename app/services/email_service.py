"""Email sending interface and implementations supporting SMTP and in-memory mock.

Follows the Dependency Inversion Principle, isolating external delivery mechanisms
behind an abstract interface with support for test assertions and retries.
"""

from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import smtplib
from typing import Any, Dict, List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailSender(ABC):
    """Abstract interface for email delivery providers."""

    @abstractmethod
    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """Send an email to a recipient.

        Args:
            to: Recipient email address.
            subject: Subject line.
            body: Plaintext email body.
            html_body: Optional HTML email body.

        Returns:
            bool: True if sent successfully, False otherwise.
        """
        pass


class MockEmailSender(EmailSender):
    """In-memory mock email sender for tests and development with fault injection."""

    def __init__(self) -> None:
        """Initialize message storage and simulation flags."""
        self.sent_messages: List[Dict[str, Any]] = []
        self.failure_mode: bool = False
        self.failures_remaining: int = 0

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """Record or simulate failures for sent email."""
        if self.failure_mode:
            logger.warning(f"[MockEmailSender] Simulated permanent failure for {to}")
            return False

        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            logger.warning(
                f"[MockEmailSender] Simulated transient failure for {to} (remaining: {self.failures_remaining})"
            )
            return False

        message_record = {
            "to": to,
            "subject": subject,
            "body": body,
            "html_body": html_body,
        }
        self.sent_messages.append(message_record)
        logger.info(f"[MockEmailSender] Successfully delivered email to {to}: {subject}")
        return True

    def get_messages(self) -> List[Dict[str, Any]]:
        """Return all sent emails."""
        return list(self.sent_messages)

    def get_messages_for(self, recipient: str) -> List[Dict[str, Any]]:
        """Return all emails sent to a specific recipient."""
        return [m for m in self.sent_messages if m["to"] == recipient]

    def clear(self) -> None:
        """Clear all stored messages and reset failure simulations."""
        self.sent_messages.clear()
        self.failure_mode = False
        self.failures_remaining = 0


class SMTPEmailSender(EmailSender):
    """Production SMTP email delivery implementation."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        from_address: Optional[str] = None,
        use_tls: Optional[bool] = None,
    ) -> None:
        """Initialize SMTP connection parameters from settings."""
        self.host = host or settings.smtp_host
        self.port = port or settings.smtp_port
        self.user = user or settings.smtp_user
        self.password = password or settings.smtp_password
        self.from_address = from_address or settings.smtp_from
        self.use_tls = settings.smtp_use_tls if use_tls is None else use_tls

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """Deliver email through SMTP server."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_address
            msg["To"] = to

            part_text = MIMEText(body, "plain", "utf-8")
            msg.attach(part_text)

            if html_body:
                part_html = MIMEText(html_body, "html", "utf-8")
                msg.attach(part_html)

            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(self.from_address, [to], msg.as_string())

            logger.info(f"[SMTPEmailSender] Sent email to {to}: {subject}")
            return True
        except Exception as exc:
            logger.error(f"[SMTPEmailSender] Failed sending email to {to}: {exc}")
            return False


# Singleton instances
_mock_email_sender = MockEmailSender()
_active_sender: Optional[EmailSender] = None


def get_email_sender() -> EmailSender:
    """Retrieve active email sender instance based on application configuration."""
    global _active_sender
    if _active_sender is not None:
        return _active_sender
    if settings.use_mock_email or not settings.smtp_user:
        return _mock_email_sender
    return SMTPEmailSender()


def set_email_sender(sender: EmailSender) -> None:
    """Explicitly inject an email sender for tests."""
    global _active_sender
    _active_sender = sender
