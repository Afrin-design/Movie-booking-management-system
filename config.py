import os
import logging

logger = logging.getLogger(__name__)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        logger.warning("[CONFIG] SECRET_KEY is not set — using insecure fallback.")
        SECRET_KEY = "bms-cinema-secret-2025-CHANGE-ME"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # ── Flask-Mail via SendGrid SMTP ────────────────────────────────────────────
    MAIL_SERVER          = "smtp.sendgrid.net"
    MAIL_PORT            = 587
    MAIL_USE_TLS         = True
    MAIL_USE_SSL         = False
    MAIL_USERNAME        = "apikey"  # Always this literal string for SendGrid
    MAIL_PASSWORD        = os.environ.get("SENDGRID_API_KEY")
    # IMPORTANT: Must match a verified Sender Identity in SendGrid
    # https://app.sendgrid.com/settings/sender_auth
    MAIL_DEFAULT_SENDER  = os.environ.get("MAIL_DEFAULT_SENDER")
    MAIL_SUPPRESS_SEND   = False
    MAIL_MAX_EMAILS      = None
    MAIL_ASCII_ATTACHMENTS = False

    if not MAIL_PASSWORD:
        logger.warning("[CONFIG] SENDGRID_API_KEY is not set. Emails will fail.")
    if not MAIL_DEFAULT_SENDER:
        logger.warning("[CONFIG] MAIL_DEFAULT_SENDER is not set. Must match a SendGrid verified sender.")


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:Afrin%409346@localhost:5432/movie_db",
    )
    # Suppress email in local dev so you don't accidentally send real emails.
    # Set DEV_SEND_MAIL=true in your local .env to actually test sending.
    MAIL_SUPPRESS_SEND = os.environ.get("DEV_SEND_MAIL", "false").lower() != "true"


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SESSION_COOKIE_SECURE   = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    MAIL_SUPPRESS_SEND      = False
<<<<<<< HEAD
    # MAIL_PASSWORD and MAIL_DEFAULT_SENDER are inherited from Config (read from env)
=======
    MAIL_PASSWORD           = os.environ.get("SENDGRID_API_KEY")
    MAIL_DEFAULT_SENDER     = os.environ.get("MAIL_DEFAULT_SENDER", "chintarapalliafrin@gmail.com")
>>>>>>> 4a2e662a34c39356771d8b7a52094f58559a0f2d


class TestingConfig(Config):
    TESTING            = True
    MAIL_SUPPRESS_SEND = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


config_map = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
    "default":     DevelopmentConfig,
}