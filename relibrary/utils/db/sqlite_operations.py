"""
SQLite数据库操作工具模块，提供SQLite数据库的高级操作功能
"""

import sqlite3
import os
import logging
from relibrary.utils.db.db_operations import DatabaseManager

class PackageDatabase:
    """软件包数据库管理类，封装特定于软件包数据的操作"""
    
    def __init__(self, db_path):
        """
        初始化软件包数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_manager = DatabaseManager(db_path)
        self.db_path = db_path
    
    def create_tables(self):
        """
        创建数据库表结构
        
        Returns:
            bool: 是否成功创建表
        """
        if not self.db_manager.connect():
            return False
        
        try:
            # 创建源码包表
            self.db_manager.execute("""
                CREATE TABLE IF NOT EXISTS source_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    homepage TEXT,
                    description TEXT,
                    distribution TEXT NOT NULL,
                    UNIQUE(name, distribution)
                )
            """)
            
            # 创建二进制包表
            self.db_manager.execute("""
                CREATE TABLE IF NOT EXISTS binary_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source_id INTEGER,
                    distribution TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES source_packages(id),
                    UNIQUE(name, distribution)
                )
            """)
            
            # 创建补丁表
            self.db_manager.execute("""
                CREATE TABLE IF NOT EXISTS patches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_name TEXT NOT NULL,
                    patch_name TEXT NOT NULL,
                    author TEXT,
                    date TEXT,
                    description TEXT,
                    content TEXT,
                    distribution TEXT NOT NULL,
                    UNIQUE(package_name, patch_name, distribution)
                )
            """)
            
            self.db_manager.commit()
            logging.info("成功创建数据库表")
            return True
        except Exception as e:
            logging.error(f"创建数据库表失败: {e}")
            return False
        finally:
            self.db_manager.close()
    
    def insert_source_package(self, name, homepage, description, distribution):
        """
        插入源码包数据
        
        Args:
            name: 软件包名称
            homepage: 主页
            description: 描述
            distribution: 发行版
            
        Returns:
            int: 插入的ID，失败则返回-1
        """
        if not self.db_manager.connect():
            return -1
        
        try:
            query = """
                INSERT OR REPLACE INTO source_packages
                (name, homepage, description, distribution)
                VALUES (?, ?, ?, ?)
            """
            
            self.db_manager.execute(query, (name, homepage, description, distribution))
            self.db_manager.commit()
            
            # 获取插入的ID
            query = "SELECT id FROM source_packages WHERE name = ? AND distribution = ?"
            result = self.db_manager.fetch_one(query, (name, distribution))
            
            if result:
                logging.info(f"成功插入源码包: {name} 在 {distribution}")
                return result[0]
            else:
                return -1
        except Exception as e:
            logging.error(f"插入源码包失败: {name} 错误: {e}")
            return -1
        finally:
            self.db_manager.close()
    
    def insert_binary_package(self, name, source_id, distribution):
        """
        插入二进制包数据
        
        Args:
            name: 软件包名称
            source_id: 源码包ID
            distribution: 发行版
            
        Returns:
            int: 插入的ID，失败则返回-1
        """
        if not self.db_manager.connect():
            return -1
        
        try:
            query = """
                INSERT OR REPLACE INTO binary_packages
                (name, source_id, distribution)
                VALUES (?, ?, ?)
            """
            
            self.db_manager.execute(query, (name, source_id, distribution))
            self.db_manager.commit()
            
            # 获取插入的ID
            query = "SELECT id FROM binary_packages WHERE name = ? AND distribution = ?"
            result = self.db_manager.fetch_one(query, (name, distribution))
            
            if result:
                logging.info(f"成功插入二进制包: {name} 在 {distribution}")
                return result[0]
            else:
                return -1
        except Exception as e:
            logging.error(f"插入二进制包失败: {name} 错误: {e}")
            return -1
        finally:
            self.db_manager.close()
    
    def insert_patch(self, package_name, patch_name, author, date, description, content, distribution):
        """
        插入补丁数据
        
        Args:
            package_name: 软件包名称
            patch_name: 补丁名称
            author: 作者
            date: 日期
            description: 描述
            content: 内容
            distribution: 发行版
            
        Returns:
            int: 插入的ID，失败则返回-1
        """
        if not self.db_manager.connect():
            return -1
        
        try:
            query = """
                INSERT OR REPLACE INTO patches
                (package_name, patch_name, author, date, description, content, distribution)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            self.db_manager.execute(query, (
                package_name, patch_name, author, date, description, content, distribution
            ))
            self.db_manager.commit()
            
            # 获取插入的ID
            query = "SELECT id FROM patches WHERE package_name = ? AND patch_name = ? AND distribution = ?"
            result = self.db_manager.fetch_one(query, (package_name, patch_name, distribution))
            
            if result:
                logging.info(f"成功插入补丁: {patch_name} 到 {package_name} 在 {distribution}")
                return result[0]
            else:
                return -1
        except Exception as e:
            logging.error(f"插入补丁失败: {patch_name} 错误: {e}")
            return -1
        finally:
            self.db_manager.close()
    
    def import_packages_data(self, packages_data, distribution):
        """
        导入软件包数据到数据库
        
        Args:
            packages_data: 软件包数据字典
            distribution: 发行版
            
        Returns:
            dict: 导入结果统计
        """
        stats = {
            'source_packages': 0,
            'binary_packages': 0,
            'errors': 0
        }
        
        if not self.db_manager.connect():
            return stats
        
        try:
            for source_name, pkg_info in packages_data.items():
                # 插入源码包
                homepage = pkg_info.get('homepage', '')
                description = pkg_info.get('description', '')
                
                source_id = self.insert_source_package(
                    source_name, homepage, description, distribution
                )
                
                if source_id != -1:
                    stats['source_packages'] += 1
                    
                    # 插入关联的二进制包
                    binaries = pkg_info.get('binaries', [])
                    for binary_name in binaries:
                        if self.insert_binary_package(binary_name, source_id, distribution) != -1:
                            stats['binary_packages'] += 1
                        else:
                            stats['errors'] += 1
                else:
                    stats['errors'] += 1
            
            logging.info(f"成功导入 {stats['source_packages']} 个源码包和 {stats['binary_packages']} 个二进制包")
            return stats
        except Exception as e:
            logging.error(f"导入软件包数据失败: {e}")
            return stats
        finally:
            self.db_manager.close()
    
    def import_patches_from_db(self, src_db_path, packages_list):
        """
        从另一个数据库导入补丁数据
        
        Args:
            src_db_path: 源数据库路径
            packages_list: 需要导入的软件包列表
            
        Returns:
            int: 成功导入的补丁数量
        """
        if not os.path.exists(src_db_path):
            logging.error(f"源数据库不存在: {src_db_path}")
            return 0
        
        # 连接两个数据库
        src_db = DatabaseManager(src_db_path)
        if not src_db.connect():
            return 0
        
        if not self.db_manager.connect():
            src_db.close()
            return 0
        
        successful_imports = 0
        
        try:
            # 构建IN子句的参数
            placeholders = ','.join(['?' for _ in packages_list])
            
            # 获取patches表的列名
            src_db.execute("PRAGMA table_info(patches)")
            columns = [column[1] for column in src_db.cursor.fetchall()]
            
            # 排除id字段
            columns_without_id = [col for col in columns if col.lower() != 'id']
            columns_str = ','.join(columns_without_id)
            
            # 从源数据库获取补丁数据
            query = f"SELECT {columns_str} FROM patches WHERE package_name IN ({placeholders})"
            patches_data = src_db.fetch_all(query, packages_list)
            
            if patches_data:
                # 构建INSERT语句
                placeholders = ','.join(['?' for _ in columns_without_id])
                insert_query = f"INSERT OR REPLACE INTO patches ({columns_str}) VALUES ({placeholders})"
                
                # 插入数据到目标数据库
                for patch in patches_data:
                    try:
                        self.db_manager.execute(insert_query, patch)
                        successful_imports += 1
                        logging.info(f"成功导入补丁: {patch[1]}")  # patch_name通常是第二个字段
                    except Exception as e:
                        logging.error(f"导入补丁失败: {patch[1]} 错误: {e}")
                
                self.db_manager.commit()
                logging.info(f"成功导入 {successful_imports} 个补丁")
            else:
                logging.info("没有找到需要导入的补丁")
            
            return successful_imports
        except Exception as e:
            logging.error(f"从数据库导入补丁失败: {e}")
            return successful_imports
        finally:
            src_db.close()
            self.db_manager.close()
    
    def get_package_patches(self, package_name, distribution=None):
        """
        获取指定软件包的补丁
        
        Args:
            package_name: 软件包名称
            distribution: 可选的发行版过滤
            
        Returns:
            list: 补丁列表
        """
        if not self.db_manager.connect():
            return []
        
        try:
            if distribution:
                query = """
                    SELECT id, patch_name, author, date, description
                    FROM patches
                    WHERE package_name = ? AND distribution = ?
                """
                patches = self.db_manager.fetch_all(query, (package_name, distribution))
            else:
                query = """
                    SELECT id, patch_name, author, date, description, distribution
                    FROM patches
                    WHERE package_name = ?
                """
                patches = self.db_manager.fetch_all(query, (package_name,))
            
            # 转换为字典列表
            result = []
            for patch in patches:
                if distribution:
                    patch_dict = {
                        'id': patch[0],
                        'patch_name': patch[1],
                        'author': patch[2],
                        'date': patch[3],
                        'description': patch[4]
                    }
                else:
                    patch_dict = {
                        'id': patch[0],
                        'patch_name': patch[1],
                        'author': patch[2],
                        'date': patch[3],
                        'description': patch[4],
                        'distribution': patch[5]
                    }
                result.append(patch_dict)
            
            return result
        except Exception as e:
            logging.error(f"获取软件包补丁失败: {package_name} 错误: {e}")
            return []
        finally:
            self.db_manager.close()

def merge_packages_databases(db1_path, db2_path, common_packages_file):
    """
    合并两个软件包数据库的补丁数据
    
    Args:
        db1_path: 源数据库路径
        db2_path: 目标数据库路径
        common_packages_file: 包含公共软件包列表的文件
        
    Returns:
        int: 成功合并的补丁数量
    """
    # 读取公共软件包列表
    try:
        with open(common_packages_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            diff_packages = []
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    diff_packages.extend(line.strip().split(';'))
    except Exception as e:
        logging.error(f"读取公共软件包列表失败: {e}")
        return 0
    
    # 确保有软件包可以导入
    if not diff_packages:
        logging.error("没有找到需要合并的软件包")
        return 0
    
    # 执行导入
    db = PackageDatabase(db2_path)
    return db.import_patches_from_db(db1_path, diff_packages)

if __name__ == "__main__":
    # 使用示例
    db_path = "package_data.db"
    db = PackageDatabase(db_path)
    db.create_tables()
    
    # 可以在这里添加导入示例
    print(f"数据库 {db_path} 初始化完成") 