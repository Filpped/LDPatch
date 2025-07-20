import sqlite3
import logging
import os

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
    
    def connect(self):

        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            return True
        except Exception as e:
            return False
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
    
    def execute(self, query, params=None):
        try:
            if params:
                result = self.cursor.execute(query, params)
            else:
                result = self.cursor.execute(query)
            return result
        except Exception as e:
            return None
    
    def commit(self):
        try:
            self.conn.commit()
            return True
        except Exception as e:
            return False
    
    def fetch_all(self, query, params=None):
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            result = self.cursor.fetchall()
            return result
        except Exception as e:
            return []
    
    def fetch_one(self, query, params=None):
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            result = self.cursor.fetchone()
            return result
        except Exception as e:
            return None
    
    def table_exists(self, table_name):
        try:
            query = f"SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            self.cursor.execute(query, (table_name,))
            return self.cursor.fetchone() is not None
        except Exception as e:
            return False
    
    def get_table_columns(self, table_name):
        try:
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [column[1] for column in self.cursor.fetchall()]
            return columns
        except Exception as e:
            return [] 