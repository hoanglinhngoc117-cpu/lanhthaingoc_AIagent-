"""
Module: core/guardrails.py
Step 2: Lớp bảo vệ an ninh & Kiểm duyệt truy vấn
- AST Parser / Lexer: Chặn tuyệt đối INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, ATTACH
- RBAC Enforcement: Tự động inject điều kiện phân quyền vùng miền theo Role
- PII Masking: Che giấu tên khách hàng, số điện thoại
- Auto-Retry Loop: Tự sửa lỗi truy vấn tối đa 3 lần
"""
import sqlite3
import re
from typing import Dict, Any, List, Tuple
import pandas as pd

class SecurityViolationError(Exception):
    """Ngoại lệ khi vi phạm chính sách bảo mật Data Warehouse"""
    pass

class DataGuardrails:
    # Danh sách các từ khóa DDL / DML bị cấm tuyệt đối
    FORBIDDEN_KEYWORDS = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", 
        "CREATE", "REPLACE", "ATTACH", "DETACH", "PRAGMA", "EXEC", 
        "EXECUTE", "GRANT", "REVOKE"
    ]

    # Danh sách các cột chứa PII cần che dấu
    PII_COLUMNS = {
        "customer_name": lambda val: re.sub(r"(?<=^.).*(?=.$)", "***", str(val)) if val and val != "None" else "N/A",
        "customer_phone": lambda val: str(val)[:3] + "****" + str(val)[-2:] if val and len(str(val)) >= 6 else "***"
    }

    def __init__(self, db_path: str = "db/enterprise_dw.sqlite"):
        self.db_path = db_path

    def inspect_ast_and_sanitize(self, sql_query: str) -> bool:
        """
        Kiểm tra câu SQL qua bộ phân tích từ vựng (AST/Token validation).
        Đảm bảo câu lệnh CHỈ LÀ READ-ONLY (SELECT) và không có SQL Injection nguy hiểm.
        """
        # Chuẩn hóa khoảng trắng và chuyển chữ hoa để kiểm tra
        normalized = sql_query.strip().upper()
        
        # Bắt buộc bắt đầu bằng SELECT hoặc WITH (cho CTE)
        if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
            raise SecurityViolationError(f"Chặn bảo mật AST: Câu truy vấn phải bắt đầu bằng SELECT hoặc WITH. Phát hiện: {sql_query[:20]}")

        # Kiểm tra sự xuất hiện của các từ khóa cấm
        for keyword in self.FORBIDDEN_KEYWORDS:
            # Dùng regex word boundary để tránh bắt nhầm (vd: 'UPDATED_AT' không bị coi là 'UPDATE')
            pattern = rf"\b{keyword}\b"
            if re.search(pattern, normalized):
                raise SecurityViolationError(f"Chặn bảo mật AST: Phát hiện hành vi ghi/xóa bị cấm tuyệt đối: [{keyword}]")

        # Chặn multiple statements (dấu chấm phẩy ngăn câu lệnh kép)
        statements = [s for s in sql_query.split(";") if s.strip()]
        if len(statements) > 1:
            raise SecurityViolationError("Chặn bảo mật: Không cho phép thực thi đa câu lệnh (Multiple statements injection).")

        return True

    def apply_rbac(self, sql_query: str, user_role: str) -> str:
        """
        Thực thi chính sách phân quyền theo vai trò (Role-Based Access Control).
        Ví dụ: Manager_Region_North chỉ được xem dữ liệu các cửa hàng thuộc region = 'North'.
        """
        if user_role == "Admin_Global":
            return sql_query # Toàn quyền xem

        if user_role == "Manager_Region_North":
            # Nếu câu lệnh truy vấn bảng orders hoặc stores, tiêm filter vùng miền
            if "WHERE" in sql_query.upper():
                # Tiêm thêm điều kiện vào sau WHERE
                rbac_condition = " stores.region = 'North' AND "
                modified_sql = re.sub(r"(?i)\bWHERE\b", f"WHERE {rbac_condition}", sql_query, count=1)
            else:
                # Nếu chưa có WHERE, tiêm WHERE trước GROUP BY hoặc ORDER BY
                target = "ORDER BY" if "ORDER BY" in sql_query.upper() else ("GROUP BY" if "GROUP BY" in sql_query.upper() else ";")
                if target != ";":
                    pattern = rf"(?i)\b{target}\b"
                    modified_sql = re.sub(pattern, f"WHERE stores.region = 'North' {target}", sql_query, count=1)
                else:
                    modified_sql = sql_query.rstrip(";") + " WHERE stores.region = 'North'"
            return modified_sql

        return sql_query

    def mask_pii(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tự động che giấu thông tin cá nhân khách hàng (PII Masking)
        """
        df_masked = df.copy()
        for col, mask_func in self.PII_COLUMNS.items():
            if col in df_masked.columns:
                df_masked[col] = df_masked[col].apply(mask_func)
        return df_masked

    def execute_query_with_retry(self, sql_generator_func, max_retries: int = 3, user_role: str = "Manager_Region_North") -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Vòng lặp tự sửa lỗi (Auto-Retry Loop):
        Nếu câu SQL bị lỗi cú pháp hoặc ngoại lệ, Agent đọc lỗi và thử sinh lại tối đa 3 lần.
        """
        logs = []
        last_error = None
        attempt = 1

        while attempt <= max_retries:
            sql_attempt = sql_generator_func(attempt, last_error)
            logs.append({"attempt": attempt, "sql": sql_attempt, "status": "PENDING"})

            try:
                # 1. Kiểm duyệt AST
                self.inspect_ast_and_sanitize(sql_attempt)
                
                # 2. Áp dụng RBAC
                safe_sql = self.apply_rbac(sql_attempt, user_role)
                logs[-1]["safe_sql"] = safe_sql

                # 3. Thực thi an toàn
                conn = sqlite3.connect(self.db_path)
                df = pd.read_sql_query(safe_sql, conn)
                conn.close()

                # 4. Che PII
                df = self.mask_pii(df)
                
                logs[-1]["status"] = "SUCCESS"
                logs[-1]["row_count"] = len(df)
                return df, logs

            except Exception as e:
                last_error = str(e)
                logs[-1]["status"] = "FAILED"
                logs[-1]["error"] = last_error
                attempt += 1

        raise RuntimeError(f"Auto-retry thất bại sau {max_retries} lần thử. Lỗi cuối: {last_error}")
