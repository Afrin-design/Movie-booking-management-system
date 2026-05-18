from database.db import db
from datetime import datetime


class CarouselSlide(db.Model):
    __tablename__ = "carousel_slides"

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    movie_id      = db.Column(db.String(20), db.ForeignKey("movies.movie_id", ondelete="CASCADE"), nullable=False)
    badge_label   = db.Column(db.String(50), default="NOW SHOWING")
    image_url     = db.Column(db.Text)
    image_data    = db.Column(db.Text)   # base64 data URI
    trailer_url   = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    movie = db.relationship("Movie", backref=db.backref("carousel_slides", lazy="dynamic"))

    def __repr__(self):
        return f"<CarouselSlide {self.id} | {self.movie_id}>"
