from database.db import db

class Screen(db.Model):
    __tablename__ = "screens"

    screen_id  = db.Column(db.String(20), primary_key=True)
    theater_id = db.Column(
        db.String(20),
        db.ForeignKey("theaters.theater_id", ondelete="CASCADE"),
        nullable=False,
    )

    screen_number = db.Column(db.Integer, nullable=False)
    total_seats   = db.Column(db.Integer, nullable=False)
    gold_seats    = db.Column(db.Integer, nullable=False, default=0)
    silver_seats  = db.Column(db.Integer, nullable=False, default=0)
    general_seats = db.Column(db.Integer, nullable=False, default=0)

    theater = db.relationship("Theater", back_populates="screens")
    shows   = db.relationship("Show",    back_populates="screen", lazy="select")
    seats   = db.relationship(
        "Seat", back_populates="screen", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def seat_summary(self):
        return (
            f"Gold: {self.gold_seats} · "
            f"Silver: {self.silver_seats} · "
            f"General: {self.general_seats}"
        )

    def __repr__(self):
        return (
            f"<Screen {self.screen_id} | "
            f"Theater {self.theater_id} | "
            f"Screen #{self.screen_number} | "
            f"{self.total_seats} seats>"
        )
