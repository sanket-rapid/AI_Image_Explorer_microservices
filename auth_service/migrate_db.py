#!/usr/bin/env python3
"""
Database migration script to initialize users table
"""
from sqlalchemy import create_engine, text
from database import DATABASE_URL, Base, engine
from models import User

def migrate_database():
    print(f"Connecting to database: {DATABASE_URL}")
    
    # Create tables defined in models
    Base.metadata.create_all(bind=engine)
    
    with engine.connect() as conn:
        try:
            # Check if users table exists
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'users'
            """))
            if result.fetchone():
                print("Users table already exists.")
            else:
                print("Users table created successfully.")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate_database()