import sqlite3
import os
import logging
from relibrary.utils.db.db_operations import DatabaseManager

class PackageDatabase:
    
    def __init__(self, db_path):
        self.db_manager = DatabaseManager(db_path)
        self.db_path = db_path
    
    def create_tables(self):
        if not self.db_manager.connect():
            return False
        
        try:
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
            return True
        except Exception as e:
            return False
        finally:
            self.db_manager.close()
    
    def insert_source_package(self, name, homepage, description, distribution):
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
            
            query = "SELECT id FROM source_packages WHERE name = ? AND distribution = ?"
            result = self.db_manager.fetch_one(query, (name, distribution))
            
            if result:
                return result[0]
            else:
                return -1
        except Exception as e:
            return -1
        finally:
            self.db_manager.close()
    
    def insert_binary_package(self, name, source_id, distribution):
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
            
            query = "SELECT id FROM binary_packages WHERE name = ? AND distribution = ?"
            result = self.db_manager.fetch_one(query, (name, distribution))
            
            if result:
                return result[0]
            else:
                return -1
        except Exception as e:
            return -1
        finally:
            self.db_manager.close()
    
    def insert_patch(self, package_name, patch_name, author, date, description, content, distribution):
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
            
            query = "SELECT id FROM patches WHERE package_name = ? AND patch_name = ? AND distribution = ?"
            result = self.db_manager.fetch_one(query, (package_name, patch_name, distribution))
            
            if result:
                return result[0]
            else:
                return -1
        except Exception as e:
            return -1
        finally:
            self.db_manager.close()
    
    def import_packages_data(self, packages_data, distribution):
        stats = {
            'source_packages': 0,
            'binary_packages': 0,
            'errors': 0
        }
        
        if not self.db_manager.connect():
            return stats
        
        try:
            for source_name, pkg_info in packages_data.items():
                homepage = pkg_info.get('homepage', '')
                description = pkg_info.get('description', '')
                
                source_id = self.insert_source_package(
                    source_name, homepage, description, distribution
                )
                
                if source_id != -1:
                    stats['source_packages'] += 1
                    
                    binaries = pkg_info.get('binaries', [])
                    for binary_name in binaries:
                        if self.insert_binary_package(binary_name, source_id, distribution) != -1:
                            stats['binary_packages'] += 1
                        else:
                            stats['errors'] += 1
                else:
                    stats['errors'] += 1
            return stats
        except Exception as e:
            return stats
        finally:
            self.db_manager.close()
    
    def import_patches_from_db(self, src_db_path, packages_list):
        if not os.path.exists(src_db_path):
            return 0
        
        src_db = DatabaseManager(src_db_path)
        if not src_db.connect():
            return 0
        
        if not self.db_manager.connect():
            src_db.close()
            return 0
        
        successful_imports = 0
        
        try:
            placeholders = ','.join(['?' for _ in packages_list])
            
            src_db.execute("PRAGMA table_info(patches)")
            columns = [column[1] for column in src_db.cursor.fetchall()]
            
            columns_without_id = [col for col in columns if col.lower() != 'id']
            columns_str = ','.join(columns_without_id)
            
            query = f"SELECT {columns_str} FROM patches WHERE package_name IN ({placeholders})"
            patches_data = src_db.fetch_all(query, packages_list)
            
            if patches_data:
                placeholders = ','.join(['?' for _ in columns_without_id])
                insert_query = f"INSERT OR REPLACE INTO patches ({columns_str}) VALUES ({placeholders})"
                
                for patch in patches_data:
                    try:
                        self.db_manager.execute(insert_query, patch)
                        successful_imports += 1
                    except Exception as e:
                        logging.error("error")
                
                self.db_manager.commit()
            else:
                logging.info("error")
            
            return successful_imports
        except Exception as e:
            return successful_imports
        finally:
            src_db.close()
            self.db_manager.close()
    
    def get_package_patches(self, package_name, distribution=None):
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
            return []
        finally:
            self.db_manager.close()

def merge_packages_databases(db1_path, db2_path, common_packages_file):
    try:
        with open(common_packages_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            diff_packages = []
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    diff_packages.extend(line.strip().split(';'))
    except Exception as e:
        return 0
    
    if not diff_packages:
        return 0
    
    db = PackageDatabase(db2_path)
    return db.import_patches_from_db(db1_path, diff_packages)

if __name__ == "__main__":
    db_path = "package_data.db"
    db = PackageDatabase(db_path)
    db.create_tables()
    