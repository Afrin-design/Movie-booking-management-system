from database.db import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = "users"

    user_id              = db.Column(db.String(20), primary_key=True)
    name                 = db.Column(db.String(100), nullable=False)
    email                = db.Column(db.String(150), unique=True, nullable=False)
    phone_number         = db.Column(db.String(20))
    date_of_birth        = db.Column(db.Date)
    password_hash        = db.Column(db.String(256))
    role                 = db.Column(db.String(20), default="user")
    city                 = db.Column(db.String(100))
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    # One owner → one brand only
    brand_id             = db.Column(db.Integer, db.ForeignKey("theater_brands.id"), nullable=True, index=True)
    status               = db.Column(db.String(20), default="Active", nullable=False, server_default="Active")

    bookings       = db.relationship("Booking", back_populates="user", lazy="select")
    payments       = db.relationship("Payment", back_populates="user", lazy="select")
    reviews        = db.relationship("Review",  back_populates="user", lazy="select")
    owned_theaters = db.relationship("Theater", back_populates="owner", lazy="select", foreign_keys="Theater.owner_id")
    brand          = db.relationship("TheaterBrand", back_populates="owners", foreign_keys=[brand_id])

    def get_id(self):
        return self.user_id

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.user_id} | {self.email} | {self.role}>"
