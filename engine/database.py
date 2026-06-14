import os
import sqlite3
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Handles connections to the Mythos database.
    Supports SQLite locally and can be extended for PostgreSQL/MySQL
    using environment variables (e.g. for GitHub Actions or production).
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("MYTHOS_DB_PATH", "mythos.db")
        self.conn: Optional[Any] = None

    def connect(self):
        """Establish a connection to the database."""
        db_type = os.environ.get("MYTHOS_DB_TYPE", "sqlite")
        
        if db_type == "sqlite":
            try:
                self.conn = sqlite3.connect(self.db_path)
                self.conn.row_factory = sqlite3.Row
                logger.info(f"Connected to SQLite database at {self.db_path}")
            except Exception as e:
                logger.error(f"Failed to connect to SQLite: {e}")
                raise
        elif db_type == "postgres":
            # For PostgreSQL, we'd use psycopg2
            # Provided as a template for "connecting with github repo"
            try:
                import psycopg2
                host = os.environ.get("DB_HOST")
                user = os.environ.get("DB_USER")
                password = os.environ.get("DB_PASSWORD")
                dbname = os.environ.get("DB_NAME")
                self.conn = psycopg2.connect(
                    host=host,
                    user=user,
                    password=password,
                    dbname=dbname
                )
                logger.info("Connected to PostgreSQL database")
            except ImportError:
                logger.error("psycopg2 not installed. Run 'pip install psycopg2-binary'")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL: {e}")
                raise
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    def execute(self, query: str, params: tuple = ()):
        """Execute a query and commit."""
        if not self.conn:
            self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            self.conn.commit()
            return cursor
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            if self.conn:
                self.conn.rollback()
            raise

    def fetch_all(self, query: str, params: tuple = ()):
        """Fetch all results for a query."""
        if not self.conn:
            self.connect()
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
