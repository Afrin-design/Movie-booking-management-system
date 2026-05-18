from database.db import db
from datetime import datetime, time as _time_type, date as _date_type


def _parse_time(val):
    """Convert a string like '23:00' or '09:30:00' to a Python time object."""
    if val is None:
        return None
    if isinstance(val, _time_type):
        return val
    s = str(val).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    return None  # unparseable


def _parse_date(val):
    """Convert a string like '2026-05-09' to a Python date object."""
    if val is None:
        return None
    if isinstance(val, (_date_type, datetime)):
        return val if isinstance(val, _date_type) else val.date()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


class Show(db.Model):
    __tablename__ = "shows"

    show_id    = db.Column(db.String(20), primary_key=True)
    movie_id   = db.Column(db.String(20), db.ForeignKey("movies.movie_id",   ondelete="CASCADE"), nullable=False)
    theater_id = db.Column(db.String(20), db.ForeignKey("theaters.theater_id", ondelete="CASCADE"), nullable=False)
    screen_id  = db.Column(db.String(20), db.ForeignKey("screens.screen_id",  ondelete="CASCADE"), nullable=False)

    show_date        = db.Column(db.Date,        nullable=False)
    start_time       = db.Column(db.String(10))   # stored as "HH:MM" string
    price_per_ticket = db.Column(db.Numeric(10, 2))
    available_seats  = db.Column(db.Integer)

    movie    = db.relationship("Movie",   back_populates="shows")
    theater  = db.relationship("Theater", back_populates="shows")
    screen   = db.relationship("Screen",  back_populates="shows")
    bookings = db.relationship(
        "Booking", back_populates="show", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True
    )

    # ── Safe accessors that always return proper Python objects ──────────────

    @property
    def show_date_obj(self):
        """Always returns a Python date object (never a string)."""
        return _parse_date(self.show_date)

    @property
    def start_time_obj(self):
        """Always returns a Python time object (never a string)."""
        return _parse_time(self.start_time)

    @property
    def start_time_display(self):
        """Returns formatted time string like '11:00 PM'."""
        t = self.start_time_obj
        return t.strftime("%I:%M %p") if t else (self.start_time or "—")

    @property
    def show_date_display(self):
        """Returns formatted date string like '09 May 2026'."""
        d = self.show_date_obj
        return d.strftime("%d %b %Y") if d else str(self.show_date or "—")

    def __repr__(self):
        return f"<Show {self.show_id} | Movie {self.movie_id} | {self.show_date} {self.start_time}>"
