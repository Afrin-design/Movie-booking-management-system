from database.db import db


class Seat(db.Model):
    __tablename__ = "seats"

    # Primary Key
    seat_id = db.Column(db.String(20), primary_key=True)          # e.g. ST_1

    # Foreign Keys
    booking_id = db.Column(
        db.String(20),
        db.ForeignKey("bookings.booking_id", ondelete="SET NULL"),
        nullable=True
    )
    screen_id = db.Column(
        db.String(20),
        db.ForeignKey("screens.screen_id", ondelete="CASCADE"),
        nullable=False
    )

    # Columns
    seat_number = db.Column(db.String(10))                        # e.g. B18, C10
    seat_type   = db.Column(db.String(20))                        # VIP / Premium / Regular
    charges     = db.Column(db.Numeric(10, 2))                    # extra charge on top of ticket price
    status      = db.Column(db.String(20))                        # Available / Booked / Reserved

    # Relationships
    booking = db.relationship("Booking", back_populates="seats")
    screen  = db.relationship("Screen",  back_populates="seats")

    def __repr__(self):
        return f"<Seat {self.seat_id} | {self.seat_type} {self.seat_number} | {self.status}>"
