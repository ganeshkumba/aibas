
import sqlite3

def clean_inventory():
    print("Cleaning up malformed Inventory data...")
    conn = None
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        # Check count before
        cursor.execute("SELECT Count(*) FROM inventory_stockmovement")
        cnt_move = cursor.fetchone()[0]
        cursor.execute("SELECT Count(*) FROM inventory_product")
        cnt_prod = cursor.fetchone()[0]
        
        print(f"Found {cnt_prod} Products and {cnt_move} Movements with potential ID issues.")
        
        # Delete
        cursor.execute("DELETE FROM inventory_stockmovement")
        cursor.execute("DELETE FROM inventory_product")
        
        conn.commit()
        print("Successfully deleted malformed Inventory data.")
        
    except Exception as e:
        print(f"Error cleaning DB: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    clean_inventory()
