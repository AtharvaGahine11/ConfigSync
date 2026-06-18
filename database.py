import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.db')

def get_db_connection():
    """Returns a connection to the SQLite database with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable Write-Ahead Logging (WAL) for better concurrent performance
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Initializes the database tables and inserts seed data for services."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. configurations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configurations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            version INTEGER DEFAULT 1,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. config_history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            version INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            changed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 3. services table (stores distributed nodes status)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
            current_version INTEGER DEFAULT 0,
            term INTEGER DEFAULT 0,
            voted_for TEXT
        )
    ''')
    
    # Insert seed services if they do not exist
    seed_services = [
        ('service_a', 'Service A', 'FOLLOWER', 'ALIVE', 0, 0, None),
        ('service_b', 'Service B', 'FOLLOWER', 'ALIVE', 0, 0, None),
        ('service_c', 'Service C', 'FOLLOWER', 'ALIVE', 0, 0, None)
    ]
    
    for service_id, name, role, status, current_version, term, voted_for in seed_services:
        cursor.execute('''
            INSERT OR IGNORE INTO services (id, name, role, status, current_version, term, voted_for)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (service_id, name, role, status, current_version, term, voted_for))
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    print(f"Initializing SQLite database at: {DB_PATH}")
    init_db()
    print("Database initialization complete.")
