from database import Base, engine
from models import User, History

Base.metadata.create_all(bind=engine)
print("Database initialized")