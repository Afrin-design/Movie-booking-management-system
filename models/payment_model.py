from database.db import db


class Payment(db.Model):
    __tablename__ = "payments"

    # Primary Key
    payment_id = db.Column(db.String(20), primary_key=True)       # e.g. PMT_1

    # Foreign Keys
    booking_id = db.Column(
        db.String(20),
        db.ForeignKey("bookings.booking_id", ondelete="CASCADE"),
        nullable=False
    )
    user_id = db.Column(
        db.String(20),
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False
    )

    # Columns
    payment_method     = db.Column(db.String(50))                 # Credit Card / UPI / etc.
    payment_date       = db.Column(db.DateTime)
    transaction_status = db.Column(db.String(50))                 # Success / Failed / Pending

    # Relationships
    booking = db.relationship("Booking", back_populates="payments")
    user    = db.relationship("User",    back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.payment_id} | Booking {self.booking_id} | {self.transaction_status}>"
