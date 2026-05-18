import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "bms-cinema-secret-2025")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # Flask-Mail — using working Gmail App Password (same as school app)
    MAIL_SERVER         = "smtp.gmail.com"
    MAIL_PORT           = 587
    MAIL_USE_TLS        = True
    MAIL_USE_SSL        = False
    MAIL_USERNAME       = os.environ.get("MAIL_USERNAME", "affu68526@gmail.com")
    MAIL_PASSWORD       = os.environ.get("MAIL_PASSWORD", "pfos jgii lfiq paln")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_USERNAME", "affu68526@gmail.com")
    MAIL_SUPPRESS_SEND  = False

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:Afrin%409346@localhost:5432/movie_db",
    )

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SESSION_COOKIE_SECURE   = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

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
