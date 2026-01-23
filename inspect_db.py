
import sqlite3

def check_table(table_name):
    print(f"\n--- {table_name} IDs ---")
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, name FROM {table_name}")
        rows = cursor.fetchall()
        for row in rows:
            print(f"ID: {repr(row[0])}, Name: {row[1]}")
    except Exception as e:
        print(f"Error reading {table_name}: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_table("inventory_product")
    check_table("core_business")
