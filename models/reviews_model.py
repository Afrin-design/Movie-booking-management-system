from database.db import db


class Review(db.Model):
    __tablename__ = "reviews"

    # Primary Key
    review_id = db.Column(db.String(20), primary_key=True)        # e.g. REV_1

    # Foreign Keys
    user_id = db.Column(
        db.String(20),
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False
    )
    movie_id = db.Column(
        db.String(20),
        db.ForeignKey("movies.movie_id", ondelete="CASCADE"),
        nullable=False
    )

    # Columns
    rating      = db.Column(db.Numeric(3, 1))                     # 0.0 – 10.0
    review_text = db.Column(db.Text)
    review_date = db.Column(db.DateTime)

    # Relationships
    user  = db.relationship("User",  back_populates="reviews")
    movie = db.relationship("Movie", back_populates="reviews")

    def __repr__(self):
        return f"<Review {self.review_id} | Movie {self.movie_id} | Rating {self.rating}>"
