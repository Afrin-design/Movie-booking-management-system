from flask_sqlalchemy import SQLAlchemy

# Single shared SQLAlchemy instance — imported by every model file
db = SQLAlchemy()
