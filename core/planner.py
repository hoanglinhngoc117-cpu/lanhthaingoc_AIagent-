"""
Module: core/planner.py
Step 2: Lập kế hoạch truy vấn (Agent Planner)
Chia nhỏ bài toán lớn thành các bước truy vấn con (Decomposition)
và sinh câu lệnh SQL chuẩn theo Semantic Layer.
"""
from typing import Dict, Any, List

class AgentPlanner:
    def __init__(self, entities: Dict[str, Any]):
        self.entities = entities

    def create_execution_plan(self) -> List[Dict[str, Any]]:
        """
        Chia nhỏ bài toán thành các sub-tasks có thứ tự phụ thuộc
        """
        date_val = self.entities["time_range"]["date"]
        limit = self.entities.get("limit", 5)

        plan = [
            {
                "step_id": 1,
                "name": "Truy vấn tỷ lệ hủy đơn theo từng cửa hàng",
                "purpose": f"Xác định xếp hạng Top {limit} cửa hàng có tỷ lệ hủy đơn cao nhất trong ngày {date_val}.",
                "generator_func": lambda attempt, err: self._gen_step_1_sql(date_val, limit, attempt, err)
            },
            {
                "step_id": 2,
                "name": "Bóc tách chi tiết đơn hủy của cửa hàng tâm điểm",
                "purpose": "Lấy chi tiết log đơn hàng và khung giờ hủy của cửa hàng có tỷ lệ hủy bất thường để phân tích chuyên sâu.",
                "generator_func": lambda attempt, err, target_store="STORE_04": self._gen_step_2_sql(date_val, target_store, attempt, err)
            },
            {
                "step_id": 3,
                "name": "Kiểm tra cảnh báo tồn kho và đồng bộ POS",
                "purpose": "Đối chiếu dữ liệu cảnh báo sai lệch kho thực tế vs POS trong ngày để tìm nguyên nhân gốc rễ.",
                "generator_func": lambda attempt, err, target_store="STORE_04": self._gen_step_3_sql(date_val, target_store, attempt, err)
            }
        ]
        return plan

    def _gen_step_1_sql(self, date_val: str, limit: int, attempt: int, error_msg: str = None) -> str:
        # Giả lập logic sinh SQL thông minh (có khả năng sửa lỗi nếu attempt > 1)
        return f"""
        SELECT 
            stores.store_id,
            stores.store_name,
            stores.region,
            COUNT(orders.order_id) as total_orders,
            SUM(CASE WHEN orders.status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders,
            ROUND(SUM(CASE WHEN orders.status = 'cancelled' THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(orders.order_id), 2) as cancellation_rate
        FROM orders
        JOIN stores ON orders.store_id = stores.store_id
        WHERE orders.order_time LIKE '{date_val}%'
        GROUP BY stores.store_id, stores.store_name, stores.region
        ORDER BY cancellation_rate DESC
        LIMIT {limit}
        """

    def _gen_step_2_sql(self, date_val: str, store_id: str, attempt: int, error_msg: str = None) -> str:
        return f"""
        SELECT 
            orders.order_id,
            orders.store_id,
            stores.store_name,
            orders.customer_name,
            orders.customer_phone,
            orders.order_time,
            orders.status,
            orders.cancel_reason,
            orders.total_amount,
            orders.is_test
        FROM orders
        JOIN stores ON orders.store_id = stores.store_id
        WHERE orders.store_id = '{store_id}'
          AND orders.order_time LIKE '{date_val}%'
        ORDER BY orders.order_time ASC
        """

    def _gen_step_3_sql(self, date_val: str, store_id: str, attempt: int, error_msg: str = None) -> str:
        return f"""
        SELECT 
            inventory_alerts.alert_id,
            inventory_alerts.store_id,
            stores.store_name,
            inventory_alerts.sku,
            inventory_alerts.alert_time,
            inventory_alerts.stock_pos,
            inventory_alerts.stock_actual,
            (inventory_alerts.stock_pos - inventory_alerts.stock_actual) as discrepancy_qty,
            inventory_alerts.discrepancy_reason
        FROM inventory_alerts
        JOIN stores ON inventory_alerts.store_id = stores.store_id
        WHERE inventory_alerts.store_id = '{store_id}'
          AND inventory_alerts.alert_time LIKE '{date_val}%'
        ORDER BY inventory_alerts.alert_time ASC
        """
