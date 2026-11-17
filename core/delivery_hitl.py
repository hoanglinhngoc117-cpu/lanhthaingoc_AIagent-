"""
Module: core/delivery_hitl.py
Step 6: Phản hồi tương tác, Cảnh báo chủ động & Human-in-the-loop
- Multi-channel delivery payload (Lark / Slack / Web)
- Proactive Alert & Approval Card: Tự động kích hoạt khi KPI vượt ngưỡng rủi ro (> 15%)
- Memory & Feedback Loop: Lưu nhận xét / điều chỉnh của người dùng để cải thiện độ chính xác
"""
import sqlite3
import json
from typing import Dict, Any, List
from datetime import datetime

class DeliveryAndHITLManager:
    def __init__(self, db_path: str = "db/enterprise_dw.sqlite"):
        self.db_path = db_path
        self._init_feedback_store()

    def _init_feedback_store(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_feedback_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_text TEXT,
            feedback_type TEXT,
            user_comment TEXT,
            adjusted_definition TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS approval_actions (
            approval_id TEXT PRIMARY KEY,
            title TEXT,
            store_id TEXT,
            action_type TEXT,
            details TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        );
        """)
        conn.commit()
        conn.close()

    def check_and_generate_proactive_alert(self, analytics_res: Dict[str, Any]) -> Dict[str, Any]:
        """
        Kiểm tra ngưỡng rủi ro (Risk Threshold). Nếu tỷ lệ hủy > 15%, tự sinh Cảnh báo khẩn cấp + Thẻ phê duyệt.
        """
        top_store = analytics_res["top_store"]
        cancel_rate = top_store["cancellation_rate"]

        alert = {
            "triggered": False,
            "threshold": 15.0,
            "severity": "NORMAL",
            "card": None
        }

        if cancel_rate >= 15.0:
            approval_id = f"APV-{top_store['store_id']}-{datetime.now().strftime('%Y%m%d%H%M')}"
            alert["triggered"] = True
            alert["severity"] = "CRITICAL"
            alert["card"] = {
                "approval_id": approval_id,
                "title": f"⚠️ CẢNH BÁO KHẨN CẤP: TỶ LỆ HỦY VƯỢT NGƯỠNG TẠI {top_store['store_name'].upper()}",
                "description": (
                    f"Tỷ lệ hủy đơn tại {top_store['store_name']} đạt **{cancel_rate}%** (ngưỡng tối đa cho phép là 15%). "
                    f"Phát hiện lỗi không đồng bộ tồn kho giữa POS và thực tế khiến khách tiếp tục đặt hàng trên App."
                ),
                "proposed_action": "Tự động khóa tạm thời 4 SKU hết hàng trên kênh Online và đẩy chu kỳ đồng bộ POS về 60 giây.",
                "target_store": top_store["store_id"],
                "actions": [
                    {"label": "✅ Phê duyệt khóa SKU & Ép đồng bộ POS", "action": "APPROVE", "style": "danger"},
                    {"label": "❌ Từ chối & Bỏ qua cảnh báo", "action": "REJECT", "style": "secondary"}
                ]
            }

            # Lưu vào DB để quản lý trạng thái phê duyệt
            self._save_approval_ticket(alert["card"])

        return alert

    def _save_approval_ticket(self, card_data: Dict[str, Any]):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO approval_actions (approval_id, title, store_id, action_type, details, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            """, (
                card_data["approval_id"],
                card_data["title"],
                card_data["target_store"],
                "EMERGENCY_SKU_LOCK",
                card_data["proposed_action"]
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Warning] Không thể lưu approval action: {e}")

    def record_feedback(self, query: str, feedback_type: str, comment: str = "", adjusted_def: str = "") -> bool:
        """
        Ghi nhận phản hồi của người dùng vào Memory Store để học hỏi dài hạn
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO agent_feedback_memory (query_text, feedback_type, user_comment, adjusted_definition)
            VALUES (?, ?, ?, ?)
            """, (query, feedback_type, comment, adjusted_def))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving feedback: {e}")
            return False

    def resolve_approval(self, approval_id: str, decision: str) -> bool:
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
            UPDATE approval_actions
            SET status = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE approval_id = ?
            """, (decision, approval_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating approval: {e}")
            return False
