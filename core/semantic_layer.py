"""
Module: core/semantic_layer.py
Step 1: Tiếp nhận & Hiểu ý định (Intent & Context Parsing)
- Entity Extraction: thời gian, khu vực, nhóm hàng, chỉ số KPI
- Semantic Layer / Data Catalog: Map từ ngôn ngữ tự nhiên sang Schema & Công thức chuẩn
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
import re

class SemanticLayer:
    """
    Data Catalog và Semantic Layer chứa từ điển dữ liệu doanh nghiệp (Single Source of Truth)
    """
    CATALOG = {
        "tables": {
            "orders": {
                "description": "Bảng ghi nhận tất cả đơn hàng phát sinh trên toàn hệ thống",
                "columns": {
                    "order_id": "Mã đơn hàng duy nhất",
                    "store_id": "Mã định danh cửa hàng (Foreign Key to stores.store_id)",
                    "customer_name": "Tên khách hàng (PII - Phải Masking)",
                    "customer_phone": "Số điện thoại khách hàng (PII - Phải Masking)",
                    "order_time": "Thời điểm đặt hàng (YYYY-MM-DD HH:MM:SS)",
                    "status": "Trạng thái đơn hàng: 'completed' (thành công) hoặc 'cancelled' (bị hủy)",
                    "cancel_reason": "Lý do hủy đơn",
                    "total_amount": "Tổng giá trị đơn hàng (VNĐ)",
                    "is_test": "Cờ đánh dấu đơn test nội bộ (1 = test, 0 = đơn thật)"
                }
            },
            "stores": {
                "description": "Danh mục chi nhánh / cửa hàng trong chuỗi bán lẻ",
                "columns": {
                    "store_id": "Mã cửa hàng (Primary Key)",
                    "store_name": "Tên chi nhánh cửa hàng",
                    "region": "Vùng miền: 'North' (Miền Bắc), 'Central' (Miền Trung), 'South' (Miền Nam)",
                    "manager_role": "Vai trò quản lý phụ trách phân quyền RBAC"
                }
            },
            "inventory_alerts": {
                "description": "Nhật ký cảnh báo tồn kho và sai lệch tồn thực tế với POS",
                "columns": {
                    "alert_id": "Mã cảnh báo",
                    "store_id": "Mã cửa hàng phát sinh cảnh báo",
                    "sku": "Mã sản phẩm / SKU",
                    "alert_time": "Thời điểm ghi nhận cảnh báo",
                    "stock_pos": "Tồn kho hiển thị trên phần mềm POS",
                    "stock_actual": "Tồn kho thực tế kiểm đếm tại quầy",
                    "discrepancy_reason": "Nguyên nhân ghi nhận sai lệch"
                }
            }
        },
        "kpi_formulas": {
            "cancellation_rate": {
                "name": "Tỷ lệ hủy đơn",
                "formula": "COUNT(CASE WHEN status = 'cancelled' THEN 1 END) * 100.0 / COUNT(*)",
                "unit": "%",
                "mandatory_filters": ["is_test = 0", "total_amount > 0"]
            },
            "revenue": {
                "name": "Doanh thu thuần",
                "formula": "SUM(total_amount)",
                "unit": "VNĐ",
                "mandatory_filters": ["status = 'completed'", "is_test = 0"]
            },
            "inventory_discrepancy": {
                "name": "Chênh lệch tồn kho",
                "formula": "SUM(stock_pos - stock_actual)",
                "unit": "sản phẩm"
            }
        },
        "synonyms": {
            "hủy đơn": "cancellation_rate",
            "tỷ lệ hủy": "cancellation_rate",
            "cancel": "cancellation_rate",
            "doanh số": "revenue",
            "doanh thu": "revenue",
            "tiền": "revenue",
            "tồn kho": "inventory_discrepancy",
            "hết hàng": "inventory_discrepancy"
        }
    }

    def __init__(self, current_time: str = "2026-11-17 08:00:00"):
        self.current_dt = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")

    def parse_intent(self, user_query: str) -> Dict[str, Any]:
        """
        Phân tách thực thể (Entity Extraction) & Đối chiếu Semantic Layer
        """
        query_lower = user_query.lower()
        entities = {
            "raw_query": user_query,
            "time_range": None,
            "target_metric": None,
            "dimension": None,
            "limit": None,
            "mapped_tables": [],
            "kpi_definition": None
        }

        # 1. Parse Time
        if "hôm qua" in query_lower or "yesterday" in query_lower:
            yesterday_dt = self.current_dt - timedelta(days=1)
            date_str = yesterday_dt.strftime("%Y-%m-%d")
            entities["time_range"] = {
                "type": "exact_day",
                "date": date_str,
                "start": f"{date_str} 00:00:00",
                "end": f"{date_str} 23:59:59",
                "display": f"Hôm qua ({date_str})"
            }
        elif "hôm nay" in query_lower or "today" in query_lower:
            date_str = self.current_dt.strftime("%Y-%m-%d")
            entities["time_range"] = {
                "type": "exact_day",
                "date": date_str,
                "start": f"{date_str} 00:00:00",
                "end": f"{date_str} 23:59:59",
                "display": f"Hôm nay ({date_str})"
            }
        else:
            # Default to yesterday for demo context
            yesterday_dt = self.current_dt - timedelta(days=1)
            date_str = yesterday_dt.strftime("%Y-%m-%d")
            entities["time_range"] = {
                "type": "exact_day",
                "date": date_str,
                "start": f"{date_str} 00:00:00",
                "end": f"{date_str} 23:59:59",
                "display": f"Hôm qua ({date_str})"
            }

        # 2. Parse Metrics via Synonyms
        for syn, kpi_key in self.CATALOG["synonyms"].items():
            if syn in query_lower:
                entities["target_metric"] = kpi_key
                entities["kpi_definition"] = self.CATALOG["kpi_formulas"][kpi_key]
                break

        if not entities["target_metric"]:
            entities["target_metric"] = "cancellation_rate"
            entities["kpi_definition"] = self.CATALOG["kpi_formulas"]["cancellation_rate"]

        # 3. Parse Dimension
        if "cửa hàng" in query_lower or "store" in query_lower or "chi nhánh" in query_lower:
            entities["dimension"] = "stores.store_name"
            entities["mapped_tables"].extend(["orders", "stores"])
        
        if "nguyên nhân" in query_lower or "lý do" in query_lower or "tại sao" in query_lower:
            entities["mapped_tables"].append("inventory_alerts")

        # 4. Parse Limit / Top
        match_top = re.search(r"top\s*(\d+)", query_lower)
        if match_top:
            entities["limit"] = int(match_top.group(1))
        else:
            entities["limit"] = 5

        # Deduplicate tables
        entities["mapped_tables"] = list(set(entities["mapped_tables"]))

        return entities
