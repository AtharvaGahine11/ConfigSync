import sqlite3
import datetime
from database import get_db_connection
import watcher

class WriteBlockedException(Exception):
    """Exception raised when a write operation is attempted without an active leader."""
    pass

def get_active_leader():
    """
    Checks if there is an active, ALIVE leader in the services table.
    Returns the leader's service record or None.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM services WHERE role = 'LEADER' AND status = 'ALIVE'")
    leader = cursor.fetchone()
    conn.close()
    return leader

def enforce_leader():
    """Enforces that an active leader must exist for write operations."""
    leader = get_active_leader()
    if not leader:
        watcher.log_event("SYSTEM", "Write operation blocked: No active leader found.", "WARNING")
        raise WriteBlockedException("Write operation blocked: No active leader elected. Re-electing leader...")
    return leader

def get_all_configs():
    """Retrieves all current configurations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM configurations ORDER BY key ASC")
    configs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return configs

def get_config_by_id(config_id):
    """Retrieves a single configuration by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM configurations WHERE id = ?", (config_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_config_by_key(key):
    """Retrieves a single configuration by key."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM configurations WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_config(key, value, description):
    """
    Creates a new configuration.
    Requires an active leader. Increments global version.
    """
    leader = enforce_leader()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if key already exists
        cursor.execute("SELECT * FROM configurations WHERE key = ?", (key,))
        if cursor.fetchone():
            raise Exception(f"Configuration key '{key}' already exists.")
            
        # Insert configuration
        cursor.execute('''
            INSERT INTO configurations (key, value, description, version, updated_at)
            VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
        ''', (key, value, description))
        
        config_id = cursor.lastrowid
        
        # Insert history record
        cursor.execute('''
            INSERT INTO config_history (config_id, key, value, version, change_type, changed_at)
            VALUES (?, ?, ?, 1, 'CREATE', CURRENT_TIMESTAMP)
        ''', (config_id, key, value))
        
        conn.commit()
        
        watcher.log_event("API", f"Config '{key}' created with value='{value}' via Leader ({leader['name']})", "SUCCESS")
        watcher.trigger_config_update()
        return config_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_config(config_id, key, value, description):
    """
    Updates an existing configuration and logs it to history.
    Requires an active leader.
    """
    leader = enforce_leader()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get current version
        cursor.execute("SELECT * FROM configurations WHERE id = ?", (config_id,))
        current = cursor.fetchone()
        if not current:
            raise Exception("Configuration not found.")
            
        new_version = current['version'] + 1
        
        # Update configurations
        cursor.execute('''
            UPDATE configurations
            SET key = ?, value = ?, description = ?, version = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (key, value, description, new_version, config_id))
        
        # Insert history record
        cursor.execute('''
            INSERT INTO config_history (config_id, key, value, version, change_type, changed_at)
            VALUES (?, ?, ?, ?, 'UPDATE', CURRENT_TIMESTAMP)
        ''', (config_id, key, value, new_version))
        
        conn.commit()
        
        watcher.log_event("API", f"Config '{key}' updated to version {new_version} via Leader ({leader['name']})", "SUCCESS")
        watcher.trigger_config_update()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_config(config_id):
    """
    Deletes a configuration and adds a DELETE record to the history.
    Requires an active leader.
    """
    leader = enforce_leader()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM configurations WHERE id = ?", (config_id,))
        current = cursor.fetchone()
        if not current:
            raise Exception("Configuration not found.")
            
        # Delete from configurations
        cursor.execute("DELETE FROM configurations WHERE id = ?", (config_id,))
        
        # Insert history record for DELETE
        new_version = current['version'] + 1
        cursor.execute('''
            INSERT INTO config_history (config_id, key, value, version, change_type, changed_at)
            VALUES (?, ?, ?, ?, 'DELETE', CURRENT_TIMESTAMP)
        ''', (config_id, current['key'], current['value'], new_version))
        
        conn.commit()
        
        watcher.log_event("API", f"Config '{current['key']}' deleted via Leader ({leader['name']})", "SUCCESS")
        watcher.trigger_config_update()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def rollback_to_revision(revision_id):
    """
    Point-in-Time Recovery: Reverts all configurations to the exact state they had at history ID `revision_id`.
    Requires an active leader.
    """
    leader = enforce_leader()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if the revision exists
        cursor.execute("SELECT * FROM config_history WHERE id = ?", (revision_id,))
        target_rev = cursor.fetchone()
        if not target_rev:
            raise Exception(f"Revision {revision_id} not found in history.")
            
        # Get the latest state of each configuration key at or before revision_id
        cursor.execute('''
            SELECT h.config_id, h.key, h.value, h.version, h.change_type
            FROM config_history h
            INNER JOIN (
                SELECT key, MAX(id) as max_id
                FROM config_history
                WHERE id <= ?
                GROUP BY key
            ) latest ON h.id = latest.max_id
        ''', (revision_id,))
        
        historical_configs = cursor.fetchall()
        
        # 1. Clear current active configurations
        cursor.execute("DELETE FROM configurations")
        
        # 2. Rebuild configurations based on historical state
        for row in historical_configs:
            if row['change_type'] != 'DELETE':
                # Restore the key
                # We fetch a description if we can find one in history or insert a generic rollback note
                description = f"Restored from revision {revision_id}"
                
                # Check if it was modified later, let's keep version incrementing
                # In standard etcd/zookeeper, version is incremented globally
                cursor.execute('''
                    INSERT INTO configurations (id, key, value, description, version, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (row['config_id'], row['key'], row['value'], description, row['version'] + 1))
                
                # Add a ROLLBACK event to the history log
                cursor.execute('''
                    INSERT INTO config_history (config_id, key, value, version, change_type, changed_at)
                    VALUES (?, ?, ?, ?, 'ROLLBACK', CURRENT_TIMESTAMP)
                ''', (row['config_id'], row['key'], row['value'], row['version'] + 1))
                
            else:
                # If the latest change was delete, it should remain deleted
                pass
                
        conn.commit()
        
        watcher.log_event("API", f"Global configuration rolled back to revision {revision_id} via Leader ({leader['name']})", "SUCCESS")
        watcher.trigger_config_update()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_history():
    """Retrieves the full configuration audit log history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM config_history ORDER BY id DESC")
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return history

def get_current_revision():
    """Returns the current system revision (maximum ID in config_history) or 0."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(id) as max_id FROM config_history")
    row = cursor.fetchone()
    conn.close()
    return row['max_id'] if row and row['max_id'] is not None else 0
