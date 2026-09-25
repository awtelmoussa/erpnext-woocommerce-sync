import sqlite3
import os
import threading
import json
from utils import logger

DB_FILE = "processed_orders.db"
JSON_FILE = "processed_orders.json"
lock = threading.Lock()


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_orders (
                woo_order_id TEXT PRIMARY KEY,
                sales_order TEXT,
                status TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

        # Run migration if JSON file exists
        if os.path.exists(JSON_FILE):
            logger.info(f"Migrating {JSON_FILE} to SQLite database...")
            try:
                with open(JSON_FILE, "r") as file:
                    data = json.load(file)
                
                for woo_id, details in data.items():
                    cursor.execute(
                        "INSERT OR IGNORE INTO processed_orders (woo_order_id, sales_order, status) VALUES (?, ?, ?)",
                        (str(woo_id), details.get("sales_order"), details.get("status"))
                    )
                conn.commit()
                
                # Rename the JSON file to keep a backup
                backup_name = f"{JSON_FILE}.backup"
                if os.path.exists(backup_name):
                    os.remove(backup_name)
                os.rename(JSON_FILE, backup_name)
                logger.info(f"Migration completed successfully. Backed up old JSON to {backup_name}")
            except Exception as e:
                logger.error(f"Error migrating JSON data to SQLite: {e}")
            finally:
                conn.close()
        else:
            conn.close()


# Initialize immediately when module is loaded
init_db()


def is_order_processed(woo_order_id):
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_orders WHERE woo_order_id = ?", (str(woo_order_id),))
        row = cursor.fetchone()
        conn.close()
        return row is not None


def mark_order_processed(woo_order_id, sales_order_name, status=None):
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO processed_orders (woo_order_id, sales_order, status) VALUES (?, ?, ?)",
            (str(woo_order_id), sales_order_name, status)
        )
        conn.commit()
        conn.close()


def get_processed_order(woo_order_id):
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT sales_order, status FROM processed_orders WHERE woo_order_id = ?", (str(woo_order_id),))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"sales_order": row["sales_order"], "status": row["status"]}
        return None


def check_and_lock_order(woo_order_id, woo_status):
    """
    Checks if the order is already being processed or has already reached the target status.
    If not, locks the order by setting its status to 'processing' and returns (True, old_details).
    Otherwise, returns (False, current_details).
    """
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT sales_order, status FROM processed_orders WHERE woo_order_id = ?", (str(woo_order_id),))
        row = cursor.fetchone()
        
        if row:
            old_status = row["status"]
            sales_order_name = row["sales_order"]
            details = {"sales_order": sales_order_name, "status": old_status}
            
            # Skip if it is already processing or already at the target status
            if old_status == "processing" or old_status == woo_status:
                conn.close()
                return False, details
            
            # Otherwise, set to processing to lock it for update
            cursor.execute(
                "UPDATE processed_orders SET status = 'processing' WHERE woo_order_id = ?",
                (str(woo_order_id),)
            )
            conn.commit()
            conn.close()
            return True, details
        else:
            # Create a placeholder indicating it's processing
            cursor.execute(
                "INSERT INTO processed_orders (woo_order_id, sales_order, status) VALUES (?, 'PENDING_CREATION', 'processing')",
                (str(woo_order_id),)
            )
            conn.commit()
            conn.close()
            return True, None


def unlock_order(woo_order_id, old_status=None, sales_order_name="PENDING_CREATION"):
    """
    Restores or removes the order lock status if processing failed.
    """
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        if old_status is None:
            # Never fully processed before, clean up the entry so it can be retried
            cursor.execute("DELETE FROM processed_orders WHERE woo_order_id = ?", (str(woo_order_id),))
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO processed_orders (woo_order_id, sales_order, status) VALUES (?, ?, ?)",
                (str(woo_order_id), sales_order_name, old_status)
            )
        conn.commit()
        conn.close()


def get_metadata(key, default=None):
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM sync_metadata WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row["value"] if row else default


def set_metadata(key, value):
    with lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()

    