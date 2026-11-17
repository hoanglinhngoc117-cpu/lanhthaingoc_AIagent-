"""
Module: core/file_handler.py
Xử lý nhập/xuất file (Excel .xlsx, CSV) phục vụ luồng phân tích dữ liệu và báo cáo
"""
import os
import io
import pandas as pd
from typing import Dict, Any, Tuple
from datetime import datetime

class FileHandler:
    EXPORT_DIR = "exports"

    def __init__(self, export_dir: str = EXPORT_DIR):
        self.export_dir = export_dir
        os.makedirs(self.export_dir, exist_ok=True)

    def parse_uploaded_file(self, filename: str, content: bytes) -> Tuple[pd.DataFrame, str]:
        """
        Đọc file tải lên (hỗ trợ .xlsx, .xls, .csv) và chuẩn hóa thành DataFrame
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(io.BytesIO(content))
        elif ext == ".csv":
            try:
                df = pd.read_csv(io.BytesIO(content))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), encoding="latin1")
        else:
            raise ValueError(f"Định dạng file {ext} không được hỗ trợ. Vui lòng tải file .xlsx hoặc .csv")

        sheet_info = f"Đã đọc file '{filename}' thành công ({len(df)} dòng, {len(df.columns)} cột)"
        return df, sheet_info

    def generate_excel_report(self, analytics_result: Dict[str, Any], df_clean_orders: pd.DataFrame, df_stores_top: pd.DataFrame) -> str:
        """
        Xuất file Excel báo cáo tổng hợp chuẩn doanh nghiệp với nhiều Sheet:
        - Sheet 1: Executive Summary (Hiện trạng, Nguyên nhân, Đề xuất)
        - Sheet 2: Top Stores Ranking (Bảng xếp hạng tỷ lệ hủy)
        - Sheet 3: Clean Orders Data (Dữ liệu đơn hàng sau khi làm sạch)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"BaoCao_PhanTich_HuyDon_{timestamp}.xlsx"
        export_path = os.path.join(self.export_dir, export_filename)

        with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
            # 1. Sheet Tóm tắt điều hành
            summary = analytics_result["executive_summary"]
            summary_rows = [
                {"Mục": "Tiêu đề báo cáo", "Chi tiết": summary["title"]},
                {"Mục": "Thời gian xuất báo cáo", "Chi tiết": datetime.now().strftime("%d/%m/%Y %H:%M:%S")},
                {"Mục": "Kết luận nhanh", "Chi tiết": summary["raw_conclusion"]},
            ]
            for sec in summary["sections"]:
                for idx, bullet in enumerate(sec["bullets"], 1):
                    clean_b = bullet.replace("**", "").replace("`", "")
                    summary_rows.append({"Mục": f"{sec['stage']} (#{idx})", "Chi tiết": clean_b})

            df_summary = pd.DataFrame(summary_rows)
            df_summary.to_excel(writer, sheet_name="Tom_Tat_Dieu_Hanh", index=False)

            # 2. Sheet Xếp hạng Top Cửa hàng
            if df_stores_top is not None and not df_stores_top.empty:
                df_stores_top.to_excel(writer, sheet_name="Xep_Hang_Cua_Hang", index=False)

            # 3. Sheet Dữ liệu chi tiết đơn hàng sạch (đã mask PII)
            if df_clean_orders is not None and not df_clean_orders.empty:
                # Chỉ lấy các cột cần thiết cho báo cáo
                cols = [c for c in ["order_id", "store_id", "customer_name", "customer_phone", "order_time", "status", "cancel_reason", "total_amount"] if c in df_clean_orders.columns]
                df_clean_orders[cols].to_excel(writer, sheet_name="Chi_Tiet_Don_Hang", index=False)

        return export_path

    def generate_csv_report(self, df: pd.DataFrame, filename_prefix: str = "chi_tiet_don_hang") -> str:
        """
        Xuất file CSV dữ liệu chi tiết
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"{filename_prefix}_{timestamp}.csv"
        export_path = os.path.join(self.export_dir, export_filename)
        df.to_csv(export_path, index=False, encoding="utf-8-sig")
        return export_path
