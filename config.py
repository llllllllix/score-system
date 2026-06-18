"""
数据库配置文件
支持 MySQL 8.0+ 和 TiDB
"""

# MySQL 本地配置
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'wms_db',
    'charset': 'utf8mb4'
}

# TiDB 云数据库配置（示例）
TIDB_CONFIG = {
    'host': 'your-tidb-endpoint',
    'port': 4000,
    'user': 'your-tidb-user',
    'password': 'your-tidb-password',
    'database': 'wms_db',
    'charset': 'utf8mb4',
    'ssl_disabled': False  # TiDB 通常需要 SSL
}

# 当前使用的配置
DB_CONFIG = MYSQL_CONFIG  # 本地开发使用 MySQL
# DB_CONFIG = TIDB_CONFIG  # 生产部署使用 TiDB
