from database.db import db
from datetime import datetime


class Message(db.Model):
    """Stores Contact-Us form submissions. Displayed in Admin → Messages tab."""
    __tablename__ = "messages"

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), nullable=False)
    subject    = db.Column(db.String(200), nullable=True)
    body       = db.Column(db.Text,        nullable=False)
    is_read    = db.Column(db.Boolean,     default=False, nullable=False)
    created_at = db.Column(db.DateTime,    default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Message id={self.id} from={self.email} read={self.is_read}>"
