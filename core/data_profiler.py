"""
Module: core/data_profiler.py
Step 3: Làm sạch & Kiểm định chất lượng dữ liệu (Data Profiling & Quarantine)
- Kiểm tra các lỗi dữ liệu bẩn: is_test = 1, NULL critical fields, doanh thu âm, trùng lặp mã đơn
- Đẩy dữ liệu bẩn sang Data Quarantine để bảo vệ tính toàn vẹn của báo cáo
"""
import sqlite3
import json
from typing import Dict, Any, Tuple, List
import pandas as pd

class DataProfiler:
    def __init__(self, db_path: str = "db/enterprise_dw.sqlite"):
        self.db_path = db_path

    def profile_and_quarantine(self, df: pd.DataFrame, table_name: str = "orders") -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Quét dữ liệu, phát hiện bất thường và cách ly bản ghi lỗi
        """
        if df.empty:
            return df, {"total_scanned": 0, "clean_count": 0, "quarantined_count": 0, "issues": {}}

        total_scanned = len(df)
        quarantine_records = []
        clean_indices = []

        issues_summary = {
            "internal_test_orders": 0,
            "negative_amount": 0,
            "duplicate_order_id": 0,
            "missing_critical_data": 0
        }

        seen_order_ids = set()

        for idx, row in df.iterrows():
            reasons = []

            # 1. Phát hiện đơn test nội bộ (is_test == 1)
            if "is_test" in row and row["is_test"] == 1:
                reasons.append("Đơn test nội bộ (is_test = 1)")
                issues_summary["internal_test_orders"] += 1

            # 2. Phát hiện doanh thu âm
            if "total_amount" in row and pd.notnull(row["total_amount"]) and row["total_amount"] < 0:
                reasons.append(f"Doanh thu âm ({row['total_amount']} VNĐ)")
                issues_summary["negative_amount"] += 1

            # 3. Phát hiện trùng lặp mã đơn
            if "order_id" in row and pd.notnull(row["order_id"]):
                oid = row["order_id"]
                if oid in seen_order_ids:
                    reasons.append(f"Trùng lặp mã hóa đơn ({oid})")
                    issues_summary["duplicate_order_id"] += 1
                else:
                    seen_order_ids.add(oid)

            # 4. Phát hiện thiếu thông tin bắt buộc
            if "order_id" in row and pd.isnull(row["order_id"]):
                reasons.append("Mã đơn hàng bị NULL")
                issues_summary["missing_critical_data"] += 1

            if reasons:
                # Cách ly bản ghi
                quarantine_records.append({
                    "original_table": table_name,
                    "record_id": str(row.get("order_id", f"idx_{idx}")),
                    "error_type": "; ".join(reasons),
                    "raw_payload": json.dumps(row.to_dict(), default=str)
                })
            else:
                clean_indices.append(idx)

        # Lưu bản ghi lỗi vào bảng data_quarantine
        if quarantine_records:
            self._save_to_quarantine_db(quarantine_records)

        # DataFrame sạch
        df_clean = df.loc[clean_indices].copy()
        if "is_test" in df_clean.columns:
            # Drop cột kỹ thuật nếu không cần thiết
            pass

        report = {
            "total_scanned": total_scanned,
            "clean_count": len(df_clean),
            "quarantined_count": len(quarantine_records),
            "issues": issues_summary,
            "quarantine_sample": quarantine_records[:5]
        }

        return df_clean, report

    def _save_to_quarantine_db(self, records: List[Dict[str, Any]]):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            for r in records:
                cur.execute("""
                INSERT INTO data_quarantine (original_table, record_id, error_type, raw_payload)
                VALUES (?, ?, ?, ?)
                """, (r["original_table"], r["record_id"], r["error_type"], r["raw_payload"]))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Warning] Không thể lưu vào data_quarantine: {e}")
