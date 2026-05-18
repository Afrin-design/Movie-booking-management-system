from database.db import db

class Booking(db.Model):
    __tablename__ = "bookings"

    booking_id = db.Column(db.String(20), primary_key=True)
    user_id    = db.Column(db.String(20), db.ForeignKey("users.user_id", ondelete="CASCADE"),  nullable=False)
    show_id    = db.Column(db.String(20), db.ForeignKey("shows.show_id", ondelete="CASCADE"),  nullable=False)

    booking_date     = db.Column(db.DateTime)
    total_tickets    = db.Column(db.Integer)
    payment_status   = db.Column(db.String(50))   # Pending|Completed|CONFIRMED|CANCELLED|REFUNDED|EXPIRED
    # Stores the JS grid labels (e.g. "B12,B13") so we can show sold seats
    # reliably regardless of how the DB seat_number column is formatted.
    seat_labels      = db.Column(db.Text, nullable=True)

    # ── Financial fields ─────────────────────────────────────────────────────
    total_amount      = db.Column(db.Numeric(10, 2), nullable=True)          # base ticket price total
    convenience_fee   = db.Column(db.Numeric(10, 2), nullable=True)          # non-refundable (default ₹30)
    refund_amount     = db.Column(db.Numeric(10, 2), nullable=True)          # amount to be refunded

    # ── Cancellation fields ──────────────────────────────────────────────────
    cancellation_reason = db.Column(db.Text, nullable=True)
    cancelled_at        = db.Column(db.DateTime, nullable=True)
    refund_status       = db.Column(db.String(30), nullable=True)            # PENDING|APPROVED|REJECTED

    user     = db.relationship("User", back_populates="bookings")
    show     = db.relationship("Show", back_populates="bookings")
    payments = db.relationship(
        "Payment", back_populates="booking", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True
    )
    # Seats use SET NULL on delete — passive_deletes lets the DB handle it
    seats = db.relationship(
        "Seat", back_populates="booking", lazy="select",
        passive_deletes=True
    )

    def __repr__(self):
        return f"<Booking {self.booking_id} | User {self.user_id} | {self.payment_status}>"
