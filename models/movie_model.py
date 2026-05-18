from database.db import db

class Movie(db.Model):
    __tablename__ = "movies"

    movie_id     = db.Column(db.String(20), primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    genre        = db.Column(db.String(50))
    language     = db.Column(db.String(50))
    duration     = db.Column(db.Integer)
    rating       = db.Column(db.Float)
    release_date = db.Column(db.Date)
    description  = db.Column(db.Text)

    shows = db.relationship(
        "Show", back_populates="movie", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True
    )
    reviews = db.relationship(
        "Review", back_populates="movie", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self):
        return f"<Movie {self.movie_id} | {self.title}>"
