from database.db import db
from datetime import datetime, timedelta
import uuid

# Seats are locked permanently once selected — no time pressure.
# Lock is only released when: payment succeeds, user deselects the seat,
# or the user leaves the page (beforeunload beacon).
LOCK_TTL_SECONDS = 86400  # 24 hours — effectively permanent for the session


class SeatLock(db.Model):
    """
    Temporarily locks a seat while a user is in the payment flow.

    A row exists for every (show_id, seat_label) pair that is currently
    held by a user session.  Locks expire automatically after LOCK_TTL_SECONDS
    so stale entries (closed tab, abandoned session) never block seats forever.

    Lifecycle:
        1. User clicks a seat on the seat-selection page → POST /api/seats/<show_id>/lock
        2. Payment page is loading / processing              (lock kept alive)
        3a. Payment succeeds → booking created, lock row deleted
        3b. User cancels / page closes → POST /api/seats/<show_id>/release
        3c. Timer expires → lock row ignored / cleaned up on next check
    """

    __tablename__ = "seat_locks"

    lock_id    = db.Column(db.String(40), primary_key=True, default=lambda: f"LK_{uuid.uuid4().hex[:16]}")
    show_id    = db.Column(
        db.String(20),
        db.ForeignKey("shows.show_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seat_label = db.Column(db.String(20), nullable=False)   # JS grid label, e.g. "B12"
    user_id    = db.Column(
        db.String(20),
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=True,                                       # guests can lock too
    )
    session_id = db.Column(db.String(120), nullable=False)   # client-generated UUID

    locked_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    # Relationships (read-only, no cascade writes needed)
    show = db.relationship("Show", passive_deletes=True)

    # ── Composite unique constraint: one lock per (show, seat) at a time ──────
    __table_args__ = (
        db.UniqueConstraint("show_id", "seat_label", name="uq_seat_lock_show_seat"),
        db.Index("ix_seat_lock_show_expires", "show_id", "expires_at"),
    )

    # ────────────────────────────────────────────────────────────────────────
    @staticmethod
    def make_expires() -> datetime:
        return datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS)

    @property
    def is_active(self) -> bool:
        return datetime.utcnow() < self.expires_at

    def __repr__(self):
        return (
            f"<SeatLock {self.lock_id} | show={self.show_id} seat={self.seat_label} "
            f"session={self.session_id[:8]}… expires={self.expires_at}>"
        )
