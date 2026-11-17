"""
Module: core/edtech_agent.py
Engine xử lý tự động cho Doanh nghiệp Web AI Sinh viên:
Từ Yêu cầu thô -> Hồ sơ cơ hội -> Bản nháp báo giá & Thẩm định năng lực
"""
import json
import os
import re
from typing import Dict, Any

class EdTechInquiryAgent:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        with open(os.path.join(data_dir, "product_catalog.json"), "r", encoding="utf-8") as f:
            self.catalog = json.load(f)
        with open(os.path.join(data_dir, "operational_capacity.json"), "r", encoding="utf-8") as f:
            self.capacity = json.load(f)
        with open(os.path.join(data_dir, "sla_lead_time.json"), "r", encoding="utf-8") as f:
            self.sla = json.load(f)
        with open(os.path.join(data_dir, "approval_matrix.json"), "r", encoding="utf-8") as f:
            self.approval_rules = json.load(f)

    def process_inquiry(self, inquiry_text: str, sender_name: str = "Khách hàng", sender_email: str = "contact@school.edu.vn", org: str = "Trường Đại học") -> Dict[str, Any]:
        """
        Quy trình xử lý 6 giai đoạn khép kín
        """
        text_lower = inquiry_text.lower()

        # 1. Intent & Entity Extraction
        quantity = 50
        match_qty = re.search(r"(\d+)\s*(sinh viên|tài khoản|sv|user|thành viên)", text_lower)
        if match_qty:
            quantity = int(match_qty.group(1))

        # Detect product
        detected_sku = "AI-WRT-01"
        if "code" in text_lower or "lập trình" in text_lower or "đồ án" in text_lower:
            detected_sku = "AI-COD-03"
        elif "research" in text_lower or "nghiên cứu" in text_lower or "tóm tắt" in text_lower or "bài báo" in text_lower:
            detected_sku = "AI-RES-02"
        elif "slide" in text_lower or "thuyết trình" in text_lower or "presentation" in text_lower:
            detected_sku = "AI-SLD-04"
        elif "campus" in text_lower or "all-in-one" in text_lower or "trọn gói" in text_lower:
            detected_sku = "AI-CAMPUS-COMBO"

        # Detect requested discount
        discount_req = 0.0
        match_disc = re.search(r"chiết khấu\s*(\d+)%", text_lower)
        if match_disc:
            discount_req = float(match_disc.group(1))

        # Detect requested lead time
        lead_time_req = 5
        match_days = re.search(r"(\d+)\s*(ngày|hôm)", text_lower)
        if match_days:
            lead_time_req = int(match_days.group(1))

        # Detect budget
        budget = None
        match_budget = re.search(r"(\d+[\d,\.]+)\s*(triệu|tr|vnđ|đồng)", text_lower)
        if match_budget:
            raw_b = match_budget.group(1).replace(",", "").replace(".", "")
            if "triệu" in match_budget.group(2) or "tr" in match_budget.group(2):
                budget = float(raw_b) * 1000000
            else:
                budget = float(raw_b)

        # 2. Product & Standard Pricing Grounding (Bảng giá chuẩn 2026)
        prod = next((p for p in self.catalog if p["sku"] == detected_sku), self.catalog[0])
        unit_price = prod["unit_price_yearly"] if "năm" in text_lower or "1 năm" in text_lower else prod["unit_price_monthly"]
        billing_cycle = "Năm" if "năm" in text_lower or "1 năm" in text_lower else "Tháng"
        total_standard_amount = unit_price * quantity
        discount_amount = total_standard_amount * (discount_req / 100.0)
        net_amount = total_standard_amount - discount_amount

        # 3. Capacity & SLA Validation
        cap_info = self.capacity["available_capacity"].get(detected_sku, {"available_slots": 1000, "status": "In Stock"})
        has_enough_capacity = cap_info["available_slots"] >= quantity

        standard_sla_days = 5
        if quantity <= 50:
            standard_sla_days = 1
        elif quantity <= 200:
            standard_sla_days = 3
        elif quantity <= 1000:
            standard_sla_days = 5
        else:
            standard_sla_days = 10

        is_sla_violated = lead_time_req < standard_sla_days

        # 4. Policy & Approval Routing
        approval_status = "AUTO_APPROVED"
        approver_role = "Sales_Representative"
        requires_human_approval = False

        if discount_req > 20:
            approval_status = "PENDING_CEO_APPROVAL"
            approver_role = "Executive_Director (Ban Giám Đốc)"
            requires_human_approval = True
        elif discount_req > 10:
            approval_status = "PENDING_SALES_HEAD_APPROVAL"
            approver_role = "Sales_Head (Trưởng phòng Kinh doanh)"
            requires_human_approval = True

        if is_sla_violated:
            requires_human_approval = True

        # 5. Opportunity Profile Staging
        opp_id = f"OPP-202611-{abs(hash(inquiry_text)) % 9000 + 1000}"
        assigned_owner = "Antony Cardenas (Sales Manager)" if quantity >= 200 else "Sandra Perry (Senior Account Exec)"

        # 6. Draft Quotation & Response Email
        draft_email = self._generate_draft_email(
            sender_name, org, prod, quantity, billing_cycle,
            total_standard_amount, discount_req, net_amount,
            lead_time_req, standard_sla_days, is_sla_violated, budget
        )

        return {
            "opportunity_id": opp_id,
            "assigned_owner": assigned_owner,
            "organization": org,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "extracted_entities": {
                "product_sku": detected_sku,
                "product_name": prod["product_name"],
                "quantity": quantity,
                "billing_cycle": billing_cycle,
                "unit_price": unit_price,
                "requested_discount_pct": discount_req,
                "requested_lead_time_days": lead_time_req,
                "detected_budget": budget
            },
            "validation_results": {
                "total_standard_amount": total_standard_amount,
                "discount_amount": discount_amount,
                "net_amount": net_amount,
                "available_slots": cap_info["available_slots"],
                "capacity_sufficient": has_enough_capacity,
                "standard_sla_days": standard_sla_days,
                "is_sla_violated": is_sla_violated,
                "budget_matched": (budget is None) or (net_amount <= budget)
            },
            "approval_routing": {
                "requires_approval": requires_human_approval,
                "approval_status": approval_status,
                "approver_role": approver_role,
                "violation_notes": [
                    f"Chiết khấu {discount_req}% vượt thẩm quyền Sales (ngưỡng tối đa 10%)" if discount_req > 10 else None,
                    f"Thời hạn yêu cầu ({lead_time_req} ngày) gấp hơn SLA chuẩn ({standard_sla_days} ngày)" if is_sla_violated else None
                ]
            },
            "draft_email": draft_email
        }

    def _generate_draft_email(self, sender_name, org, prod, qty, cycle, standard_amt, disc_pct, net_amt, req_days, sla_days, sla_violated, budget) -> str:
        disc_text = f"- Chiết khấu ưu đãi ({disc_pct}%): -{disc_amt_str:,.0f} VNĐ\n" if disc_pct > 0 else ""
        disc_amt_str = standard_amt * (disc_pct / 100.0)

        lead_time_note = ""
        if sla_violated:
            lead_time_note = (
                f"\n⚠️ Lưu ý về tiến độ: Do quy mô {qty} tài khoản đòi hỏi phân vùng GPU Cloud riêng (SLA kỹ thuật chuẩn là {sla_days} ngày), "
                f"để đáp ứng thời hạn gấp {req_days} ngày của Quý Thầy/Cô, chúng tôi đề xuất phương án: "
                f"Bàn giao trước đợt 1 (50 tài khoản ưu tiên) trong 24 giờ tới và hoàn tất toàn bộ trong {sla_days} ngày làm việc."
            )
        else:
            lead_time_note = f"\nThời gian bàn giao cam kết: Hoàn tất trong {req_days} ngày làm việc."

        return f"""Kính gửi {sender_name} - {org},

EduAI Solutions chân thành cảm ơn Quý Thầy/Cô và Nhà trường đã quan tâm đến giải pháp hỗ trợ học tập và nghiên cứu AI cho sinh viên.

Căn cứ theo yêu cầu của Quý đơn vị, chúng tôi xin gửi bản thảo dự toán ngân sách cho gói phần mềm {prod['product_name']} như sau:

1. THÔNG TIN BÁO GIÁ:
- Sản phẩm: {prod['product_name']} (Bảng giá chuẩn 2026)
- Số lượng cấp phép: {qty} tài khoản sinh viên
- Chu kỳ sử dụng: 01 {cycle}
- Đơn giá niêm yết: {prod['unit_price_yearly'] if cycle == 'Năm' else prod['unit_price_monthly']:,.0f} VNĐ / tài khoản / {cycle}
- Tổng giá trị niêm yết: {standard_amt:,.0f} VNĐ
{disc_text}- Tổng chi phí thanh toán sau chiết khấu: {net_amt:,.0f} VNĐ (Đã bao gồm VAT và hóa đơn điện tử)

2. NĂNG LỰC HỆ THỐNG VÀ TIẾN ĐỘ BÀN GIAO:
- Tình trạng tài nguyên: Sẵn sàng cấp phát trên cụm GPU Cloud EduAI.{lead_time_note}

Nếu Quý đơn vị đồng ý với bản thảo trên, chuyên viên phụ trách hợp đồng của chúng tôi sẽ liên hệ trong vòng 2 giờ làm việc để gửi dự thảo hợp đồng điện tử.

Trân trọng,
Đội ngũ Tư vấn Giải pháp Giáo dục EduAI Platform
Hotline: 1900 8888 • Email: support@eduai.vn
"""
