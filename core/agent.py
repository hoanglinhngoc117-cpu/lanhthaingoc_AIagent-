"""
Module: core/agent.py
Enterprise BI & Analytics AI Agent - Orchestrator kết nối toàn bộ 6 giai đoạn
"""
from typing import Dict, Any, List
import sqlite3
import pandas as pd
from core.semantic_layer import SemanticLayer
from core.planner import AgentPlanner
from core.guardrails import DataGuardrails
from core.data_profiler import DataProfiler
from core.deep_analytics import DeepAnalyticsEngine
from core.narrative_viz import NarrativeAndVizGenerator
from core.delivery_hitl import DeliveryAndHITLManager
from core.file_handler import FileHandler

class EnterpriseAnalyticsAgent:
    def __init__(self, db_path: str = "db/enterprise_dw.sqlite"):
        self.db_path = db_path
        self.semantic_layer = SemanticLayer()
        self.guardrails = DataGuardrails(db_path)
        self.profiler = DataProfiler(db_path)
        self.analytics_engine = DeepAnalyticsEngine()
        self.narrative_viz = NarrativeAndVizGenerator()
        self.hitl_manager = DeliveryAndHITLManager(db_path)
        self.file_handler = FileHandler()

        # Bộ nhớ đệm lưu trữ kết quả chạy gần nhất để xuất file Excel/CSV
        self.last_run_cache = {
            "result": None,
            "df_stores": None,
            "df_clean_orders": None
        }

    def execute(self, user_query: str, user_role: str = "Manager_Region_North") -> Dict[str, Any]:
        """
        Thực thi quy trình 6 bước khép kín
        """
        pipeline_trace = {}

        # -------------------------------------------------------------
        # 1. TIẾP NHẬN & HIỂU Ý ĐỊNH (Intent & Context Parsing)
        # -------------------------------------------------------------
        intent_data = self.semantic_layer.parse_intent(user_query)
        pipeline_trace["step_1_intent"] = {
            "entities": intent_data,
            "mapped_kpi": intent_data["kpi_definition"],
            "target_tables": intent_data["mapped_tables"]
        }

        # -------------------------------------------------------------
        # 2. LẬP KẾ HOẠCH & TRUY VẤN AN TOÀN (Planning & Secure Retrieval)
        # -------------------------------------------------------------
        planner = AgentPlanner(intent_data)
        execution_plan = planner.create_execution_plan()

        retrieval_results = {}
        retrieval_logs = []

        # Bước 2.1: Truy vấn xếp hạng cửa hàng
        df_stores_raw, logs_step1 = self.guardrails.execute_query_with_retry(
            execution_plan[0]["generator_func"],
            user_role=user_role
        )
        retrieval_results["stores_summary_raw"] = df_stores_raw
        retrieval_logs.append({"step": "Step 1: Top Stores", "logs": logs_step1})

        # Xác định cửa hàng bất thường nhất
        target_store_id = df_stores_raw.iloc[0]["store_id"] if not df_stores_raw.empty else "STORE_04"

        # Bước 2.2: Truy vấn log chi tiết đơn hàng (có PII)
        df_orders_raw, logs_step2 = self.guardrails.execute_query_with_retry(
            lambda att, err: execution_plan[1]["generator_func"](att, err, target_store_id),
            user_role=user_role
        )
        retrieval_results["orders_detail_raw"] = df_orders_raw
        retrieval_logs.append({"step": "Step 2: Store Detail Orders", "logs": logs_step2})

        # Bước 2.3: Truy vấn cảnh báo tồn kho
        df_alerts_raw, logs_step3 = self.guardrails.execute_query_with_retry(
            lambda att, err: execution_plan[2]["generator_func"](att, err, target_store_id),
            user_role=user_role
        )
        retrieval_results["alerts_raw"] = df_alerts_raw
        retrieval_logs.append({"step": "Step 3: Inventory Alerts", "logs": logs_step3})

        pipeline_trace["step_2_security_retrieval"] = {
            "plan_steps": [p["name"] for p in execution_plan],
            "retrieval_logs": retrieval_logs,
            "pii_masked_sample": df_orders_raw[["order_id", "customer_name", "customer_phone"]].head(3).to_dict(orient="records")
        }

        # -------------------------------------------------------------
        # 3. LÀM SẠCH & KIỂM ĐỊNH CHẤT LƯỢNG (Data Profiling & Quarantine)
        # -------------------------------------------------------------
        df_orders_clean, quarantine_report = self.profiler.profile_and_quarantine(df_orders_raw, table_name="orders")

        pipeline_trace["step_3_profiling_quarantine"] = {
            "report": quarantine_report,
            "sample_quarantined": quarantine_report["quarantine_sample"]
        }

        # -------------------------------------------------------------
        # 4. PHÂN TÍCH CHUYÊN SÂU & TÌM NGUYÊN NHÂN GỐC RỄ (Deep Analytics)
        # -------------------------------------------------------------
        analytics_result = self.analytics_engine.analyze_store_cancellations(
            df_stores_summary=df_stores_raw,
            df_target_orders=df_orders_clean,
            df_alerts=df_alerts_raw,
            target_store_id=target_store_id
        )

        pipeline_trace["step_4_deep_analytics"] = analytics_result

        # -------------------------------------------------------------
        # 5. TRỰC QUAN HÓA & TỔNG HỢP INSIGHT (Visualization & Narrative)
        # -------------------------------------------------------------
        charts = self.narrative_viz.generate_chart_specs(df_stores_raw, analytics_result)
        executive_summary = self.narrative_viz.generate_executive_summary(analytics_result)

        pipeline_trace["step_5_narrative_viz"] = {
            "charts": charts,
            "executive_summary": executive_summary
        }

        # -------------------------------------------------------------
        # 6. PHẢN HỒI TƯƠNG TÁC & CẢNH BÁO CHỦ ĐỘNG (Delivery & HITL)
        # -------------------------------------------------------------
        proactive_alert = self.hitl_manager.check_and_generate_proactive_alert(analytics_result)

        pipeline_trace["step_6_delivery_hitl"] = {
            "proactive_alert": proactive_alert,
            "channels_enabled": ["Lark Suite Webhook", "Slack Bot", "Interactive Web App"]
        }

        final_response = {
            "user_query": user_query,
            "user_role": user_role,
            "executive_summary": executive_summary,
            "charts": charts,
            "proactive_alert": proactive_alert,
            "pipeline_trace": pipeline_trace
        }

        # Lưu cache cho chức năng tải file Excel/CSV
        self.last_run_cache["result"] = final_response
        self.last_run_cache["df_stores"] = df_stores_raw
        self.last_run_cache["df_clean_orders"] = df_orders_clean

        return final_response

    def ingest_uploaded_file(self, filename: str, content: bytes) -> Dict[str, Any]:
        """
        Nhận file tải lên từ giao diện (.xlsx, .csv) và cập nhật vào bảng staging
        """
        df_uploaded, info = self.file_handler.parse_uploaded_file(filename, content)
        
        # Tải vào SQLite staging
        conn = sqlite3.connect(self.db_path)
        table_name = "uploaded_staging_" + filename.replace(".", "_").replace(" ", "_")
        df_uploaded.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()

        return {
            "status": "success",
            "message": info,
            "row_count": len(df_uploaded),
            "columns": list(df_uploaded.columns),
            "staging_table": table_name
        }

    def export_excel(self) -> str:
        """
        Xuất file Excel từ kết quả chạy gần nhất
        """
        if not self.last_run_cache["result"]:
            self.execute("Kiểm tra giúp tôi top 5 cửa hàng có tỷ lệ hủy đơn cao nhất hôm qua và nguyên nhân.")
        
        return self.file_handler.generate_excel_report(
            analytics_result=self.last_run_cache["result"],
            df_clean_orders=self.last_run_cache["df_clean_orders"],
            df_stores_top=self.last_run_cache["df_stores"]
        )

    def export_csv(self) -> str:
        """
        Xuất file CSV từ dữ liệu chi tiết
        """
        if not self.last_run_cache["result"]:
            self.execute("Kiểm tra giúp tôi top 5 cửa hàng có tỷ lệ hủy đơn cao nhất hôm qua và nguyên nhân.")
        
        df = self.last_run_cache["df_clean_orders"]
        return self.file_handler.generate_csv_report(df, filename_prefix="don_hang_sach")
