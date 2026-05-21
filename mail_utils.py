"""
mail_utils.py — CineHub email helper using SendGrid HTTP API
(Replaces Flask-Mail/SMTP which is blocked on Render free tier)
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def send_mail(
    to_email: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> bool:
    """
    Send an email via SendGrid HTTP API.
    Returns True on success, False on any failure (never raises).
    """
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        api_key = os.environ.get("SENDGRID_API_KEY")
        sender  = os.environ.get("MAIL_DEFAULT_SENDER")

        if not api_key:
            logger.error("[MAIL] SENDGRID_API_KEY is not set — email will NOT be sent.")
            return False

        if not sender:
            logger.error("[MAIL] MAIL_DEFAULT_SENDER is not set — email will NOT be sent.")
            return False

        message = Mail(
            from_email=sender,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body,
            html_content=html or body,
        )

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        if response.status_code in (200, 201, 202):
            logger.info("[MAIL] ✓ Sent '%s' → %s (status %s)", subject, to_email, response.status_code)
            return True
        else:
            logger.error("[MAIL] ✗ SendGrid returned status %s for '%s' → %s", response.status_code, subject, to_email)
            return False

    except Exception as exc:
        logger.error(
            "[MAIL] ✗ Failed '%s' → %s | %s: %s",
            subject, to_email, type(exc).__name__, exc,
        )
        return False


# ── Typed helpers ──────────────────────────────────────────────────────────────

def send_booking_confirmation(user_name: str, user_email: str, booking: dict) -> bool:
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
        f"Base Total      : Rs.{booking.get('base_total', 0):.2f}\n"
        f"Surcharge       : Rs.{booking.get('surcharge', 0):.2f}\n"
        f"Convenience Fee : Rs.{booking.get('convenience_fee', 0):.2f}\n"
        f"GST             : Rs.{booking.get('gst', 0):.2f}\n"
        f"Total Paid      : Rs.{booking.get('total_amount', 0):.2f}\n\n"
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
    subject = "Booking Cancellation — CineHub"
    body = (
        f"Hi {user_name},\n\n"
        f"Your booking #{booking_id} for '{movie_title}' has been cancelled.\n\n"
        f"Refund Amount    : Rs.{refund_amount:.2f}\n"
        f"(Convenience fee Rs.{convenience_fee:.0f} is non-refundable)\n\n"
        f"Your refund will be processed within 5-7 business days after admin approval.\n\n"
        f"— CineHub Support"
    )
    return send_mail(to_email=user_email, subject=subject, body=body)


def send_temp_password_email(
    user_name: str,
    user_email: str,
    temp_password: str,
    login_url: str = "",
) -> bool:
    subject = "Your Temporary Password — CineHub"
    body = (
        f"Hello {user_name},\n\n"
        f"A password reset was requested for your CineHub account.\n\n"
        f"Your temporary password is: {temp_password}\n\n"
        f"Please log in and change your password immediately.\n"
        + (f"Login here: {login_url}\n\n" if login_url else "\n")
        + "If you did not request this, please ignore this email.\n\n"
        f"Regards,\nCineHub Team"
    )
    return send_mail(to_email=user_email, subject=subject, body=body)