"""
数据库操作工具模块，提供SQLite数据库操作功能
"""

import sqlite3
import logging
import os

class DatabaseManager:
    """数据库管理器类，处理SQLite数据库操作"""
    
    def __init__(self, db_path):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """
        连接到数据库
        
        Returns:
            bool: 连接是否成功
        """
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            logging.info(f"成功连接到数据库: {self.db_path}")
            return True
        except Exception as e:
            logging.error(f"连接数据库失败: {self.db_path} 错误: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
            logging.info(f"关闭数据库连接: {self.db_path}")
    
    def execute(self, query, params=None):
        """
        执行SQL查询
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            cursor: 游标对象，失败则返回None
        """
        try:
            if params:
                result = self.cursor.execute(query, params)
            else:
                result = self.cursor.execute(query)
            return result
        except Exception as e:
            logging.error(f"执行SQL查询失败: {query} 错误: {e}")
            return None
    
    def commit(self):
        """
        提交事务
        
        Returns:
            bool: 提交是否成功
        """
        try:
            self.conn.commit()
            logging.info("成功提交事务")
            return True
        except Exception as e:
            logging.error(f"提交事务失败: {e}")
            return False
    
    def fetch_all(self, query, params=None):
        """
        执行查询并获取所有结果
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            list: 查询结果，失败则返回空列表
        """
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            result = self.cursor.fetchall()
            return result
        except Exception as e:
            logging.error(f"执行查询失败: {query} 错误: {e}")
            return []
    
    def fetch_one(self, query, params=None):
        """
        执行查询并获取一条结果
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            tuple: 查询结果，失败则返回None
        """
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            result = self.cursor.fetchone()
            return result
        except Exception as e:
            logging.error(f"执行查询失败: {query} 错误: {e}")
            return None
    
    def table_exists(self, table_name):
        """
        检查表是否存在
        
        Args:
            table_name: 表名
            
        Returns:
            bool: 表是否存在
        """
        try:
            query = f"SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            self.cursor.execute(query, (table_name,))
            return self.cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"检查表存在失败: {table_name} 错误: {e}")
            return False
    
    def get_table_columns(self, table_name):
        """
        获取表的列信息
        
        Args:
            table_name: 表名
            
        Returns:
            list: 列名列表，失败则返回空列表
        """
        try:
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [column[1] for column in self.cursor.fetchall()]
            return columns
        except Exception as e:
            logging.error(f"获取表列信息失败: {table_name} 错误: {e}")
            return [] 