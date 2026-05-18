from database.db import db


class TheaterBrand(db.Model):
    __tablename__ = "theater_brands"

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    brand_name = db.Column(db.String(100), nullable=False, unique=True)
    logo       = db.Column(db.String(255), nullable=True)   # URL or static path
    status     = db.Column(db.String(20), default="Active", nullable=False)

    # Relationships
    theaters = db.relationship(
        "Theater", back_populates="brand", lazy="dynamic",
        foreign_keys="Theater.brand_id"
    )
    owners = db.relationship(
        "User", back_populates="brand", lazy="select",
        foreign_keys="User.brand_id"
    )

    @property
    def theater_count(self):
        return self.theaters.count()

    def __repr__(self):
        return f"<TheaterBrand {self.id} | {self.brand_name}>"
