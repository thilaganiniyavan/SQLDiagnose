# schema_parser.py
# Clean Architecture: Interface Adapters
# Extracts schema metadata from SQLite, PostgreSQL, and MySQL databases.

import sqlite3
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("schema_parser")

class DatabaseSchemaParser:
    @staticmethod
    def parse_sqlite(db_path: str) -> Dict[str, Any]:
        """
        Parses a SQLite database and returns the internal schema dictionary representation.
        """
        logger.info(f"Parsing SQLite schema from: {db_path}")
        schema = {}
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 1. Fetch tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                schema[table.lower()] = {
                    "columns": {},
                    "primary_keys": [],
                    "foreign_keys": []
                }
                
                # 2. Fetch columns and primary keys
                cursor.execute(f'PRAGMA table_info("{table}");')
                columns_info = cursor.fetchall()
                # table_info columns: cid, name, type, notnull, dflt_value, pk
                for col in columns_info:
                    col_name = col[1].lower()
                    col_type = col[2].upper() if col[2] else "TEXT"
                    is_pk = col[5]
                    
                    schema[table.lower()]["columns"][col_name] = col_type
                    if is_pk:
                        schema[table.lower()]["primary_keys"].append(col_name)
                        
                # 3. Fetch foreign keys
                cursor.execute(f'PRAGMA foreign_key_list("{table}");')
                fk_info = cursor.fetchall()
                # foreign_key_list columns: id, seq, table, from, to, on_update, on_delete, match
                for fk in fk_info:
                    if fk[3] and fk[4]:  # from_col, to_col
                        schema[table.lower()]["foreign_keys"].append({
                            "column": fk[3].lower(),
                            "target_table": fk[2].lower(),
                            "target_column": fk[4].lower()
                        })
            
            conn.close()
        except Exception as e:
            logger.error(f"Failed to parse SQLite schema: {str(e)}")
            raise e
            
        return schema

    @staticmethod
    def parse_postgresql(conn_string: str) -> Dict[str, Any]:
        """
        Parses a PostgreSQL database and returns the internal schema dictionary representation.
        Expects a standard connection string (e.g. 'dbname=test user=postgres password=secret host=localhost')
        """
        logger.info("Parsing PostgreSQL schema...")
        schema = {}
        try:
            # Dynamically import connection library
            try:
                import psycopg2
                conn = psycopg2.connect(conn_string)
            except ImportError:
                # Fallback to pg8000 if available
                import pg8000
                conn = pg8000.connect(conn_string)
                
            cursor = conn.cursor()
            
            # 1. Fetch tables
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                schema[table.lower()] = {
                    "columns": {},
                    "primary_keys": [],
                    "foreign_keys": []
                }
                
            # 2. Fetch columns and data types
            cursor.execute(
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns WHERE table_schema = 'public';"
            )
            for row in cursor.fetchall():
                t_name = row[0].lower()
                c_name = row[1].lower()
                c_type = row[2].upper()
                if t_name in schema:
                    schema[t_name]["columns"][c_name] = c_type
                    
            # 3. Fetch primary keys
            cursor.execute(
                "SELECT kcu.table_name, kcu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "  AND tc.table_schema = kcu.table_schema "
                "WHERE tc.constraint_type = 'PRIMARY KEY';"
            )
            for row in cursor.fetchall():
                t_name = row[0].lower()
                c_name = row[1].lower()
                if t_name in schema:
                    schema[t_name]["primary_keys"].append(c_name)
                    
            # 4. Fetch foreign keys
            cursor.execute(
                "SELECT "
                "  kcu.table_name AS foreign_table, "
                "  kcu.column_name AS foreign_column, "
                "  ccu.table_name AS target_table, "
                "  ccu.column_name AS target_column "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "  AND tc.table_schema = kcu.table_schema "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY';"
            )
            for row in cursor.fetchall():
                f_table = row[0].lower()
                f_column = row[1].lower()
                t_table = row[2].lower()
                t_column = row[3].lower()
                if f_table in schema:
                    schema[f_table]["foreign_keys"].append({
                        "column": f_column,
                        "target_table": t_table,
                        "target_column": t_column
                    })
            
            conn.close()
        except Exception as e:
            logger.error(f"Failed to parse PostgreSQL schema: {str(e)}")
            raise e
            
        return schema

    @staticmethod
    def parse_mysql(conn_string_or_dict: Any) -> Dict[str, Any]:
        """
        Parses a MySQL database and returns the internal schema dictionary representation.
        Accepts a dictionary of connection parameters or a connection string.
        """
        logger.info("Parsing MySQL schema...")
        schema = {}
        try:
            # Dynamically import connection library
            try:
                import mysql.connector as mysql_driver
                if isinstance(conn_string_or_dict, dict):
                    conn = mysql_driver.connect(**conn_string_or_dict)
                else:
                    conn = mysql_driver.connect(dsn=conn_string_or_dict)
            except ImportError:
                import pymysql
                if isinstance(conn_string_or_dict, dict):
                    conn = pymysql.connect(**conn_string_or_dict)
                else:
                    conn = pymysql.connect(dsn=conn_string_or_dict)
                    
            cursor = conn.cursor()
            
            # 1. Fetch tables
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE';"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                schema[table.lower()] = {
                    "columns": {},
                    "primary_keys": [],
                    "foreign_keys": []
                }
                
            # 2. Fetch columns and data types
            cursor.execute(
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns WHERE table_schema = DATABASE();"
            )
            for row in cursor.fetchall():
                t_name = row[0].lower()
                c_name = row[1].lower()
                c_type = row[2].upper()
                if t_name in schema:
                    schema[t_name]["columns"][c_name] = c_type
                    
            # 3. Fetch primary keys
            cursor.execute(
                "SELECT table_name, column_name "
                "FROM information_schema.key_column_usage "
                "WHERE constraint_name = 'PRIMARY' AND table_schema = DATABASE();"
            )
            for row in cursor.fetchall():
                t_name = row[0].lower()
                c_name = row[1].lower()
                if t_name in schema:
                    schema[t_name]["primary_keys"].append(c_name)
                    
            # 4. Fetch foreign keys
            cursor.execute(
                "SELECT "
                "  table_name AS foreign_table, "
                "  column_name AS foreign_column, "
                "  referenced_table_name AS target_table, "
                "  referenced_column_name AS target_column "
                "FROM information_schema.key_column_usage "
                "WHERE referenced_table_name IS NOT NULL "
                "  AND table_schema = DATABASE();"
            )
            for row in cursor.fetchall():
                f_table = row[0].lower()
                f_column = row[1].lower()
                t_table = row[2].lower()
                t_column = row[3].lower()
                if f_table in schema:
                    schema[f_table]["foreign_keys"].append({
                        "column": f_column,
                        "target_table": t_table,
                        "target_column": t_column
                    })
            
            conn.close()
        except Exception as e:
            logger.error(f"Failed to parse MySQL schema: {str(e)}")
            raise e
            
        return schema

    @staticmethod
    def to_ddl(schema: Dict[str, Any]) -> str:
        """
        Converts the internal schema representation into schema DDL string format.
        """
        ddl_statements = []
        for table_name, table_info in schema.items():
            cols = []
            primary_keys = table_info.get("primary_keys", [])
            for col_name, col_type in table_info["columns"].items():
                col_str = f"{col_name} {col_type}"
                if col_name in primary_keys:
                    col_str += " PRIMARY KEY"
                cols.append(col_str)
            
            for fk in table_info.get("foreign_keys", []):
                cols.append(f"FOREIGN KEY ({fk['column']}) REFERENCES {fk['target_table']}({fk['target_column']})")
                
            cols_str = ",\n    ".join(cols)
            ddl_statements.append(f"CREATE TABLE {table_name} (\n    {cols_str}\n);")
            
        return "\n\n".join(ddl_statements)
