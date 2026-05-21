"""
mail_utils.py
─────────────
Centralised email helper for CineHub.

All email sending in the application should go through `send_mail()` or
the specialised wrappers below.  Direct use of Flask-Mail's Message object
outside this module is discouraged — it makes debugging harder.

SendGrid SMTP notes:
  • MAIL_USERNAME must literally be the string "apikey"
  • MAIL_PASSWORD must be your SendGrid API key (starts with "SG.")
  • From-address must be a verified sender in your SendGrid account
"""

import logging
from typing import Optional

from flask import current_app
from flask_mail import Message

logger = logging.getLogger(__name__)


# ── Core sender ───────────────────────────────────────────────────────────────

def send_mail(
    to_email: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> bool:
    """
    Send a plain-text (optionally HTML) email via Flask-Mail / SendGrid.

    Returns True on success, False on any failure.
    Failures are logged but never re-raised so callers keep running.
    """
    try:
        # Lazy import to avoid circular imports
        from app import mail

        if not current_app.config.get("SENDGRID_API_KEY") and \
           not current_app.config.get("MAIL_PASSWORD"):
            logger.error(
                "[MAIL] SENDGRID_API_KEY / MAIL_PASSWORD is not set. "
                "Email to '%s' will not be sent.", to_email
            )
            return False

        sender = current_app.config.get("MAIL_DEFAULT_SENDER")
        if not sender:
            logger.error("[MAIL] MAIL_DEFAULT_SENDER is not configured.")
            return False

        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=body,
            html=html,
            sender=sender,
        )

        mail.send(msg)
        logger.info("[MAIL] ✓ Sent '%s' to %s", subject, to_email)
        return True

    except Exception as exc:
        logger.error(
            "[MAIL] ✗ Failed to send '%s' to %s — %s: %s",
            subject, to_email, type(exc).__name__, exc,
        )
        return False


# ── Specialised email helpers ─────────────────────────────────────────────────

def send_booking_confirmation(user_name: str, user_email: str, booking: dict) -> bool:
    """
    Send a booking-confirmation email.

    `booking` dict keys:
        booking_id, movie_title, show_date, start_time,
        theater_name, theater_city, seats, base_total,
        surcharge, convenience_fee, gst, total_amount
    """
    subject = f"Booking Confirmed — {booking.get('movie_title', 'Your Movie')}"

    body = (
        f"Hi {user_name},\n\n"
        f"Your booking is confirmed! 🎬\n\n"
        f"Booking ID : {booking.get('booking_id')}\n"
        f"Movie      : {booking.get('movie_title')}\n"
        f"Date       : {booking.get('show_date')}\n"
        f"Time       : {booking.get('start_time')}\n"
        f"Theater    : {booking.get('theater_name')}, {booking.get('theater_city')}\n"
        f"Seats      : {booking.get('seats')}\n\n"
        f"──────────────────────────\n"
        f"Base Total      : ₹{booking.get('base_total', 0):.2f}\n"
        f"Surcharge       : ₹{booking.get('surcharge', 0):.2f}\n"
        f"Convenience Fee : ₹{booking.get('convenience_fee', 0):.2f}\n"
        f"GST             : ₹{booking.get('gst', 0):.2f}\n"
        f"──────────────────────────\n"
        f"Total Paid      : ₹{booking.get('total_amount', 0):.2f}\n\n"
        f"Enjoy the movie!\n\n"
        f"— CineHub Team"
    )

    return send_mail(to_email=user_email, subject=subject, body=body)


def send_cancellation_email(
    user_name: str,
    user_email: str,
    booking_id: str,
    movie_title: str,
    refund_amount: float,
    convenience_fee: float,
) -> bool:
    """Send a cancellation / refund-pending email."""
    subject = "Booking Cancellation — CineHub"

    body = (
        f"Hi {user_name},\n\n"
        f"Your booking #{booking_id} for '{movie_title}' has been cancelled.\n\n"
        f"Refund Amount    : ₹{refund_amount:.2f}\n"
        f"(Convenience fee ₹{convenience_fee:.0f} is non-refundable)\n\n"
        f"Your refund will be processed within 5–7 business days "
        f"after admin approval.\n\n"
        f"If you have questions, contact us at support@cinehub.com.\n\n"
        f"— CineHub Support"
    )

    return send_mail(to_email=user_email, subject=subject, body=body)


def send_temp_password_email(
    user_name: str,
    user_email: str,
    temp_password: str,
    login_url: str = "",
) -> bool:
    """Send a temporary-password / password-reset email."""
    subject = "Your Temporary Password — CineHub"

    body = (
        f"Hello {user_name},\n\n"
        f"A password reset was requested for your CineHub account.\n\n"
        f"Your temporary password is: {temp_password}\n\n"
        f"Please log in and set a new permanent password immediately.\n"
        + (f"Login: {login_url}\n\n" if login_url else "\n")
        + "If you did not request this, please ignore this email.\n\n"
        f"Regards,\nCineHub Team"
    )

    return send_mail(to_email=user_email, subject=subject, body=body)
