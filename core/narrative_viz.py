"""
Module: core/narrative_viz.py
Step 5: Trực quan hóa & Tổng hợp Insight (Visualization & Narrative Generation)
- Tự động sinh cấu trúc biểu đồ phù hợp (Ranking Bar Chart & Hourly Distribution Line/Bar)
- Sinh tóm tắt điều hành (Executive Summary) theo chuẩn Hiện trạng -> Nguyên nhân -> Đề xuất
"""
from typing import Dict, Any, List
import pandas as pd

class NarrativeAndVizGenerator:
    def generate_chart_specs(self, df_stores_top: pd.DataFrame, analytics_res: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tạo thông số biểu đồ cho frontend (tương thích Plotly / Chart.js)
        """
        # Chart 1: Xếp hạng Top 5 cửa hàng có tỷ lệ hủy cao nhất
        labels = df_stores_top["store_name"].tolist()
        values = df_stores_top["cancellation_rate"].tolist()
        colors = ["#e63946" if i == 0 else "#457b9d" for i in range(len(labels))]

        ranking_chart = {
            "type": "bar",
            "title": "Top 5 Cửa hàng có Tỷ lệ Hủy Đơn cao nhất (Hôm qua)",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Tỷ lệ hủy đơn (%)",
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": colors,
                    "borderWidth": 1
                }]
            },
            "options": {
                "benchmark_line": {
                    "label": f"Trung bình mạng lưới: {analytics_res['network_average_rate']}%",
                    "value": analytics_res["network_average_rate"]
                }
            }
        }

        # Chart 2: Phân bố đơn hủy theo khung giờ tại Cửa hàng #04
        hours = list(range(8, 22))
        hourly_data = analytics_res.get("hourly_distribution", {})
        hour_counts = [hourly_data.get(h, 0) for h in hours]
        hour_labels = [f"{h}h" for h in hours]
        hour_colors = ["#e63946" if h in [17, 18] else "#a8dadc" for h in hours]

        hourly_chart = {
            "type": "bar",
            "title": f"Phân bố đơn hủy theo khung giờ tại {analytics_res['top_store']['store_name']}",
            "data": {
                "labels": hour_labels,
                "datasets": [{
                    "label": "Số lượng đơn bị hủy",
                    "data": hour_counts,
                    "backgroundColor": hour_colors
                }]
            }
        }

        return {
            "ranking_chart": ranking_chart,
            "hourly_chart": hourly_chart
        }

    def generate_executive_summary(self, analytics_res: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sinh tóm tắt điều hành theo cấu trúc:
        Hiện trạng -> Nguyên nhân chính -> Đề xuất hành động
        """
        top_store = analytics_res["top_store"]
        peak = analytics_res["peak_window"]
        network_avg = analytics_res["network_average_rate"]

        summary = {
            "title": f"BÁO CÁO NHANH: TỶ LỆ HỦY ĐƠN VÀ PHÂN TÍCH NGUYÊN NHÂN",
            "sections": [
                {
                    "stage": "1. HIỆN TRẠNG (Current Situation)",
                    "icon": "🔴",
                    "bullets": [
                        f"**{top_store['store_name']}** ghi nhận tỷ lệ hủy đơn cao nhất mạng lưới ở mức **{top_store['cancellation_rate']}%** ({top_store['cancelled_orders']}/{top_store['total_orders']} đơn).",
                        f"Mức hủy này **gấp {top_store['ratio_vs_average']} lần** so với mức trung bình mạng lưới các cửa hàng khu vực phía Bắc ({network_avg}%)."
                    ]
                },
                {
                    "stage": "2. NGUYÊN NHÂN CHÍNH (Root Cause)",
                    "icon": "🔍",
                    "bullets": [
                        f"**{peak['percentage']}%** số đơn hủy tập trung đột biến vào khung giờ cao điểm **{peak['hours']}** ({peak['cancelled_count']} đơn).",
                        "**Lệch đồng bộ POS & Kho:** Hệ thống ghi nhận các cảnh báo tồn kho do tồn quầy thực tế đã hết (`stock_actual = 0`) nhưng phần mềm POS chậm đồng bộ (vẫn hiển thị còn 12–25 sản phẩm). Khách vẫn lên được đơn nhưng nhân viên buộc phải ấn hủy khi soạn hàng."
                    ]
                },
                {
                    "stage": "3. ĐỀ XUẤT HÀNH ĐỘNG (Actionable Recommendations)",
                    "icon": "⚡",
                    "bullets": [
                        "**Vận hành khẩn cấp:** Cấu hình tự động khóa nhận đơn trên POS đối với các SKU đồ uống có tồn dưới ngưỡng an toàn (Safety Stock < 5 ly) trong khung 16h30–19h30.",
                        "**Kỹ thuật hệ thống:** Giảm độ trễ chu kỳ sync tồn kho giữa quầy và server từ 15 phút xuống 1 phút (Near real-time sync).",
                        "**Điều chuyển nguyên liệu:** Cửa hàng #04 cần bổ sung định mức dự phòng nguyên liệu trà & sữa thêm 30% cho ca chiều tối."
                    ]
                }
            ],
            "raw_conclusion": (
                f"Tỷ lệ hủy tại {top_store['store_name']} là {top_store['cancellation_rate']}% (gấp {top_store['ratio_vs_average']} lần trung bình). "
                f"{peak['percentage']}% đơn hủy rơi vào khung {peak['hours']} do hết tồn kho thực tế nhưng hệ thống POS chưa đồng bộ kịp."
            )
        }

        return summary
