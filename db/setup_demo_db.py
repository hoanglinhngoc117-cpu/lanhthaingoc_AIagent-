"""
Module: db/setup_demo_db.py
Creates SQLite database with realistic retail enterprise data matching the demo scenario.
"""
import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "db/enterprise_dw.sqlite"

def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS orders;")
    cur.execute("DROP TABLE IF EXISTS stores;")
    cur.execute("DROP TABLE IF EXISTS inventory_alerts;")
    cur.execute("DROP TABLE IF EXISTS data_quarantine;")

    # 1. Stores Table
    cur.execute("""
    CREATE TABLE stores (
        store_id TEXT PRIMARY KEY,
        store_name TEXT NOT NULL,
        region TEXT NOT NULL,
        manager_role TEXT NOT NULL
    );
    """)

    # 2. Orders Table (Includes PII columns: customer_name, customer_phone)
    cur.execute("""
    CREATE TABLE orders (
        order_id TEXT PRIMARY KEY,
        store_id TEXT NOT NULL,
        customer_name TEXT,
        customer_phone TEXT,
        order_time TEXT NOT NULL,
        status TEXT NOT NULL,
        cancel_reason TEXT,
        total_amount REAL,
        is_test INTEGER DEFAULT 0,
        FOREIGN KEY (store_id) REFERENCES stores(store_id)
    );
    """)

    # 3. Inventory Alerts Table
    cur.execute("""
    CREATE TABLE inventory_alerts (
        alert_id TEXT PRIMARY KEY,
        store_id TEXT NOT NULL,
        sku TEXT NOT NULL,
        alert_time TEXT NOT NULL,
        stock_pos INTEGER NOT NULL,
        stock_actual INTEGER NOT NULL,
        discrepancy_reason TEXT NOT NULL,
        FOREIGN KEY (store_id) REFERENCES stores(store_id)
    );
    """)

    # 4. Data Quarantine Table (for Step 3)
    cur.execute("""
    CREATE TABLE data_quarantine (
        quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_table TEXT,
        record_id TEXT,
        error_type TEXT,
        raw_payload TEXT,
        quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Populate Stores
    stores_data = [
        ("STORE_01", "Cửa hàng Cầu Giấy #01", "North", "Manager_Region_North"),
        ("STORE_02", "Cửa hàng Ba Đình #02", "North", "Manager_Region_North"),
        ("STORE_03", "Cửa hàng Đống Đa #03", "North", "Manager_Region_North"),
        ("STORE_04", "Cửa hàng Hoàn Kiếm #04", "North", "Manager_Region_North"),
        ("STORE_05", "Cửa hàng Hai Bà Trưng #05", "North", "Manager_Region_North"),
        ("STORE_06", "Cửa hàng Thanh Xuân #06", "North", "Manager_Region_North"),
        ("STORE_07", "Cửa hàng Q1 Sài Gòn #07", "South", "Manager_Region_South"),
    ]
    cur.executemany("INSERT INTO stores VALUES (?, ?, ?, ?)", stores_data)

    # Date anchor: "yesterday" relative to 2026-11-17 is 2026-11-16
    yesterday = "2026-11-16"
    random.seed(42)

    orders = []
    order_idx = 1

    first_names = ["Nguyễn Văn", "Trần Thị", "Lê Hoàng", "Phạm Minh", "Vũ Mai", "Đỗ Quỳnh", "Bùi Tấn"]
    last_names = ["An", "Bình", "Cường", "Dung", "Hải", "Khánh", "Linh", "Nam", "Phương", "Thảo"]

    # Generate orders for yesterday across North stores
    for store_id, name, region, _ in stores_data:
        if region != "North":
            continue

        num_orders = 250
        # If Store #04: make cancellation rate ~18.4% with cluster in 17h-19h
        is_store_4 = (store_id == "STORE_04")

        for _ in range(num_orders):
            cust_name = f"{random.choice(first_names)} {random.choice(last_names)}"
            cust_phone = f"09{random.randint(10000000, 99999999)}"
            order_id = f"ORD-20261116-{order_idx:05d}"
            order_idx += 1

            if is_store_4:
                # 82% of cancels are during 17:00 - 18:59
                r = random.random()
                if r < 0.184:  # Cancelled
                    status = "cancelled"
                    if random.random() < 0.82:
                        hour = random.choice([17, 18])
                        cancel_reason = "out_of_stock_pos_sync_delay"
                    else:
                        hour = random.choice([8, 9, 10, 11, 14, 15, 20])
                        cancel_reason = "customer_change_mind"
                else:
                    status = "completed"
                    hour = random.randint(8, 21)
                    cancel_reason = None
            else:
                # Normal stores: cancel rate ~5-6%
                if random.random() < 0.055:
                    status = "cancelled"
                    cancel_reason = random.choice(["customer_change_mind", "delay_delivery", "out_of_stock"])
                else:
                    status = "completed"
                    cancel_reason = None
                hour = random.randint(8, 21)

            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            order_time = f"{yesterday} {hour:02d}:{minute:02d}:{second:02d}"
            amount = round(random.uniform(150000, 1200000), -3)

            orders.append((
                order_id, store_id, cust_name, cust_phone, order_time,
                status, cancel_reason, amount, 0
            ))

    # Add exactly 14 internal test orders (is_test = 1) across stores
    for i in range(14):
        test_order_id = f"TEST-20261116-{i+1:03d}"
        orders.append((
            test_order_id,
            random.choice(["STORE_01", "STORE_02", "STORE_03", "STORE_04", "STORE_05"]),
            f"QC Tester {i+1}",
            "0900000000",
            f"{yesterday} 10:{random.randint(10,50):02d}:00",
            random.choice(["completed", "cancelled"]),
            "internal_test_sample",
            0.0,
            1  # is_test = True
        ))

    # Add 2 dirty anomaly records for Data Profiling & Quarantine demonstration
    orders.append((
        "BAD-ORD-NULL-001", "STORE_02", None, None,
        f"{yesterday} 12:00:00", "cancelled", None, -50000.0, 0 # Negative amount
    ))
    orders.append((
        "ORD-20261116-00001", "STORE_01", "Trùng Lặp", "0911111111",
        f"{yesterday} 13:00:00", "completed", None, 100000.0, 0 # Duplicate ID
    ))

    # Insert ignoring duplicates to let our quarantine engine catch dirty data
    for o in orders:
        try:
            cur.execute("""
            INSERT INTO orders (order_id, store_id, customer_name, customer_phone, order_time, status, cancel_reason, total_amount, is_test)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, o)
        except sqlite3.IntegrityError:
            # Table primary key caught duplicate, simulate dirty staging
            pass

    # Insert Inventory Alerts specifically for Store #04 between 17h and 19h
    inventory_alerts = [
        ("ALT-001", "STORE_04", "SKU-BEV-TRA-SUA-01", f"{yesterday} 17:15:22", 18, 0, "POS chưa đồng bộ tồn kho thực tế tại quầy (Out of stock physical)"),
        ("ALT-002", "STORE_04", "SKU-BEV-TRA-DAO-02", f"{yesterday} 17:42:05", 12, 0, "POS ghi nhận còn 12 ly, kho quầy hết nguyên liệu"),
        ("ALT-003", "STORE_04", "SKU-SNK-BANH-MI-03", f"{yesterday} 18:05:11", 15, 2, "Lệch tồn kho thực tế vs POS do hệ thống POS chậm sync"),
        ("ALT-004", "STORE_04", "SKU-BEV-CA-PHE-04", f"{yesterday} 18:30:44", 25, 0, "Cháy hàng giờ cao điểm, POS chậm cập nhật trạng thái tạm ngưng"),
        ("ALT-005", "STORE_02", "SKU-BEV-TRA-SUA-01", f"{yesterday} 14:10:00", 5, 5, "Cảnh báo ngưỡng tồn kho thấp (đã nhập bổ sung kịp thời)")
    ]
    cur.executemany("INSERT INTO inventory_alerts VALUES (?, ?, ?, ?, ?, ?, ?)", inventory_alerts)

    conn.commit()
    conn.close()
    print(f"[OK] Database initialized successfully at {db_path} with {len(orders)} orders and {len(inventory_alerts)} alerts.")

if __name__ == "__main__":
    init_db()
