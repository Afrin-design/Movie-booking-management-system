from database.db import db

class Theater(db.Model):
    __tablename__ = "theaters"

    theater_id = db.Column(db.String(20), primary_key=True)
    name       = db.Column(db.String(150), nullable=False)
    location   = db.Column(db.String(200))
    city       = db.Column(db.String(100))
    state      = db.Column(db.String(100))
    status     = db.Column(db.String(20), default="Active", nullable=False, server_default="Active")
    owner_id   = db.Column(db.String(20), db.ForeignKey("users.user_id"), nullable=True)
    brand_id   = db.Column(db.Integer, db.ForeignKey("theater_brands.id"), nullable=True, index=True)

    # cascade="all, delete-orphan" → SQLAlchemy deletes child rows automatically
    # passive_deletes=True        → trust the DB-level ON DELETE CASCADE for bulk ops
    screens = db.relationship(
        "Screen", back_populates="theater", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True
    )
    shows = db.relationship(
        "Show", back_populates="theater", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True
    )
    owner = db.relationship("User", back_populates="owned_theaters", foreign_keys=[owner_id])
    brand = db.relationship("TheaterBrand", back_populates="theaters", foreign_keys=[brand_id])

    def __repr__(self):
        return f"<Theater {self.theater_id} | {self.name}, {self.city}>"
