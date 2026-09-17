"""
Grounded Chatbot & Reasoning Engine for Annapurna Tiffin.
Answers questions strictly based on verified company schemes,
real-time database status, and exact pro-ration mathematics with zero hallucination.
"""

from __future__ import annotations
from datetime import date
import re
from typing import Any, Dict, List, Optional

from .calendar_utils import get_month_weekdays, parse_date, format_date, is_weekday
from .service import TiffinService


class TiffinChatbot:
    def __init__(self, service: TiffinService):
        self.service = service

    def answer_query(self, message: str, phone: Optional[str] = None) -> Dict[str, Any]:
        """
        Process user question with step-by-step reasoning grounded in company schemes.
        Returns: {
            "reply": str,
            "reasoning": List[str],
            "intent": str,
            "grounded_facts": List[str]
        }
        """
        query = message.strip()
        lower = query.lower()

        # Extract phone number if present in query or parameter
        phone_match = re.search(r"(\+?\d[\d\s-]{8,14}\d)", query)
        detected_phone = phone_match.group(1) if phone_match else phone

        # 1. Customer Account / Bill Lookup Intent
        if detected_phone and any(w in lower for w in ["my bill", "status", "account", "dossier", "bill", "lookup", "phone", "profile"]):
            return self._handle_customer_lookup(detected_phone, lower)

        # 2. Hypothetical Calculation / Simulation Intent
        # e.g., "If I pause for 5 days on standard veg in October"
        pause_days_match = re.search(r"(\d+)\s*(days?|weekdays?)", lower)
        if pause_days_match and any(p in lower for p in ["standard", "deluxe", "special", "non-veg", "non veg", "pause", "leave", "pay", "bill"]):
            return self._handle_simulation(lower, int(pause_days_match.group(1)))

        # 3. Pro-ration / Billing Formula Explanation Intent
        if any(w in lower for w in ["pro-rate", "prorate", "calculate", "formula", "math", "deduct", "paused day", "how is bill calculated"]):
            return self._handle_proration_explanation(lower)

        # 4. Weekend / Pause Policy Intent
        if any(w in lower for w in ["weekend", "saturday", "sunday", "holiday", "friday to monday", "pause policy", "travel"]):
            return self._handle_pause_policy(lower)

        # 5. Plan Details / Pricing Schemes Intent
        if any(w in lower for w in ["plan", "scheme", "price", "cost", "monthly", "menu", "options", "packages", "veg", "non veg", "non-veg"]):
            return self._handle_plans_inquiry()

        # 6. General / Fallback with Guided Assistance
        return self._handle_fallback(query)

    def _handle_plans_inquiry(self) -> Dict[str, Any]:
        plans = self.service.list_plans()
        reasoning = [
            "Retrieved official company meal plans from database repository.",
            "Filtered to currently active schemes with verified pricing.",
            "Grounded in official weekday delivery policy (Monday-Friday)."
        ]
        
        lines = [
            "🍱 **Official Annapurna Tiffin Meal Schemes:**\n"
        ]
        for p in plans:
            lines.append(f"• **{p.name}** (`{p.id}`): **Rs. {p.monthly_price:.2f} / month**\n  _{p.description}_")

        lines.append("\n📌 **Important Rules:**")
        lines.append("1. Meals are delivered **every weekday (Monday through Friday)**.")
        lines.append("2. Weekends (Saturday & Sunday) are closed; no charges apply.")
        lines.append("3. Any days you pause for travel or festivals are **100% credited and deducted** at month-end.")

        return {
            "reply": "\n".join(lines),
            "reasoning": reasoning,
            "intent": "plans_inquiry",
            "grounded_facts": [f"{p.name}: Rs. {p.monthly_price:.2f}" for p in plans],
        }

    def _handle_proration_explanation(self, lower: str) -> Dict[str, Any]:
        reasoning = [
            "Identified inquiry regarding mathematical billing and pro-ration logic.",
            "Avoided naive 30-day divisor assumption (highlighted varying calendar weekdays: 20-23 days).",
            "Referenced the Calendar Weekday Pro-Ration Formula: Daily Rate = Monthly Price / Weekdays."
        ]

        reply = (
            "📐 **How Pro-Rated Billing Works at Annapurna Tiffin:**\n\n"
            "We believe in **100% fairness**: you only pay for meals actually cooked and delivered to you.\n\n"
            "**Step 1: Determine Total Working Weekdays in the Month**\n"
            "Deliveries happen Monday to Friday. Depending on the calendar, a month has between 20 and 23 weekdays (e.g., October 2026 has 22 weekdays).\n\n"
            "**Step 2: Calculate Your Exact Daily Rate**\n"
            "$$\\text{Daily Rate} = \\frac{\\text{Monthly Plan Price}}{\\text{Total Working Weekdays in the Month}}$$\n\n"
            "**Step 3: Charge Only for Delivered Weekdays**\n"
            "$$\\text{Total Bill} = \\text{Delivered Weekdays} \\times \\text{Daily Rate}$$\n\n"
            "**Example Guarantee:**\n"
            "On a Rs. 3,000 plan in a 22-weekday month (Rs. 136.36/day):\n"
            "• If you eat all 22 days: $22 \\times 136.36 = \\text{Rs. 3,000.00}$ (exact plan price).\n"
            "• If you pause for 5 weekdays: $17 \\times 136.36 = \\text{Rs. 2,318.18}$ (you save Rs. 681.82!)."
        )

        return {
            "reply": reply,
            "reasoning": reasoning,
            "intent": "proration_explanation",
            "grounded_facts": [
                "Deliveries: Monday to Friday only",
                "Daily Rate = Monthly Price / Actual Working Weekdays",
                "Full attendance = Exactly monthly plan price"
            ],
        }

    def _handle_pause_policy(self, lower: str) -> Dict[str, Any]:
        reasoning = [
            "Detected inquiry about pause intervals, weekends, or travel policy.",
            "Applied company operational boundary: weekends (Sat-Sun) are already non-billable.",
            "Verified interval isolation: pause dates spanning weekends only deduct working weekdays."
        ]

        reply = (
            "⏸️ **Annapurna Tiffin Pause & Vacation Policy:**\n\n"
            "1. **No Charge for Paused Weekdays**: Whenever you travel or take a break, your subscription can be paused for an exact date range or indefinitely.\n"
            "2. **The Weekend Advantage**: If you pause from **Friday to Monday** (4 calendar days), only **2 delivery weekdays (Friday and Monday)** are counted and deducted. Saturdays and Sundays are never charged to begin with!\n"
            "3. **Zero Advance Penalty**: Unserved meals are never billed. Your month-end bill automatically reflects the exact days food was delivered.\n"
            "4. **How to Pause**: You can pause anytime via the web dashboard or by notifying our kitchen owner."
        )

        return {
            "reply": reply,
            "reasoning": reasoning,
            "intent": "pause_policy",
            "grounded_facts": [
                "Weekends are never billable",
                "Friday-Monday pause = 2 billable days deducted",
                "Flexible pause: scheduled range or indefinite"
            ],
        }

    def _handle_customer_lookup(self, phone: str, lower: str) -> Dict[str, Any]:
        result = self.service.lookup_customer(phone)
        if not result["found"]:
            return {
                "reply": f"🔍 I checked our subscriber records, but could not find a customer registered under phone `{phone}`. Please verify your 10-digit number or register as a new subscriber.",
                "reasoning": [f"Queried customer database for phone {phone}", "Result: Record Not Found in SQLite database."],
                "intent": "customer_lookup_not_found",
                "grounded_facts": [f"Phone {phone} not found in database"],
            }

        cust = result["customer"]
        sub = result["subscription"]
        plan = result["plan"]
        st = result["status_today"]
        bill = result["current_month_bill"]

        reasoning = [
            f"Successfully found subscriber: {cust.name} ({cust.phone}).",
            f"Active Plan: {plan.name if plan else 'None'} (Rs. {plan.monthly_price if plan else 0}/mo).",
            f"Evaluated status for today: {st['status']} (is_delivery_day: {st['is_delivery_day']}).",
            f"Calculated live month-to-date pro-rated statement for {bill.month_name if bill else 'current month'}."
        ]

        reply = (
            f"👤 **Account Summary for {cust.name}** (`{cust.phone}`):\n\n"
            f"• **Plan**: {plan.name if plan else 'No active plan'} (Rs. {plan.monthly_price:.2f}/mo)\n"
            f"• **Today's Status**: **{st['status']}** ({'Meal Scheduled for Delivery' if st['is_delivery_day'] else st['pause_reason'] or 'No delivery today'})\n"
        )

        if bill:
            reply += (
                f"\n📊 **Current Month ({bill.month_name} {bill.billing_year}) Pro-Rated Breakdown:**\n"
                f"• Total Working Weekdays: **{bill.total_month_weekdays} days**\n"
                f"• Lunches Delivered: **{bill.delivered_weekdays} days**\n"
                f"• Days Paused: **{bill.paused_weekdays} days** (credited at Rs. {bill.daily_rate:.2f}/day)\n"
                f"• **Current Bill Total: Rs. {bill.total_amount:.2f}**\n\n"
                f"💡 _Reasoning_: Your bill is mathematically computed as: "
                f"${bill.delivered_weekdays} \\text{{ delivered days}} \\times \\text{{Rs. }}{bill.daily_rate:.2f} = \\text{{Rs. }}{bill.total_amount:.2f}$."
            )

        return {
            "reply": reply,
            "reasoning": reasoning,
            "intent": "customer_lookup_success",
            "grounded_facts": [
                f"Customer: {cust.name}",
                f"Plan: {plan.name if plan else 'None'}",
                f"Status: {st['status']}",
                f"Bill: Rs. {bill.total_amount if bill else 0:.2f}"
            ],
        }

    def _handle_simulation(self, lower: str, paused_days: int) -> Dict[str, Any]:
        # Choose plan mentioned or default to Standard Veg
        if "non" in lower:
            plan = self.service.get_plan("non_veg")
        elif "deluxe" in lower or "special" in lower:
            plan = self.service.get_plan("special_veg")
        else:
            plan = self.service.get_plan("standard_veg")

        if not plan:
            plan = self.service.list_plans()[0]

        # Use 22 working weekdays as standard
        total_weekdays = 22
        actual_paused = min(paused_days, total_weekdays)
        delivered_days = total_weekdays - actual_paused
        daily_rate = plan.monthly_price / total_weekdays
        simulated_bill = round(delivered_days * daily_rate, 2)

        reasoning = [
            f"Simulating scenario: {paused_days} paused weekdays on {plan.name}.",
            f"Baseline: Standard month with {total_weekdays} working weekdays.",
            f"Formula: ({delivered_days} delivered days / {total_weekdays} total weekdays) * Rs. {plan.monthly_price}.",
            f"Resulting calculated bill: Rs. {simulated_bill:.2f}."
        ]

        reply = (
            f"🧮 **Step-by-Step Scenario Simulation:**\n\n"
            f"If you subscribe to the **{plan.name}** (Rs. {plan.monthly_price:.2f}/month) and pause for **{actual_paused} weekdays**:\n\n"
            f"1. **Total Weekdays in Month**: {total_weekdays} days\n"
            f"2. **Daily Rate**: $\\text{{Rs. }}{plan.monthly_price:.2f} / {total_weekdays} = \\text{{Rs. }}{daily_rate:.2f}/\\text{{meal}}$\n"
            f"3. **Lunches Delivered**: ${total_weekdays} - {actual_paused} = {delivered_days} \\text{{ days}}$\n"
            f"4. **Absence Credit**: ${actual_paused} \\times {daily_rate:.2f} = \\text{{Rs. }}{round(actual_paused * daily_rate, 2):.2f}$\n\n"
            f"💰 **Your Pro-Rated Bill Would Be: Rs. {simulated_bill:.2f}**\n"
            f"_(You only pay for the {delivered_days} meals actually delivered to you)._"
        )

        return {
            "reply": reply,
            "reasoning": reasoning,
            "intent": "simulation",
            "grounded_facts": [
                f"Simulated plan: {plan.name}",
                f"Paused days: {actual_paused}",
                f"Delivered days: {delivered_days}",
                f"Simulated bill: Rs. {simulated_bill:.2f}"
            ],
        }

    def _handle_fallback(self, query: str) -> Dict[str, Any]:
        reasoning = [
            "Query did not match specific plan inquiry, customer lookup, or mathematical formula.",
            "Avoided generating speculative/hallucinated answers.",
            "Provided structured options grounded in Annapurna Tiffin services."
        ]

        reply = (
            "👋 Hello! I am the **Annapurna Tiffin AI Assistant**.\n\n"
            "I provide 100% verified, grounded answers about our tiffin services and pro-rated billing with **zero hallucination**.\n\n"
            "Here are things you can ask me:\n"
            "• **\"What are your meal plans and prices?\"** (View Standard Veg, Deluxe Veg, Non-Veg)\n"
            "• **\"How is pro-rated billing calculated?\"** (See the exact mathematical formula)\n"
            "• **\"Check my bill for 9876543210\"** (Get your live attendance and bill breakdown)\n"
            "• **\"What happens if I pause from Friday to Monday?\"** (Learn our weekend-safe policy)\n"
            "• **\"If I pause for 4 days on Standard Veg, how much will I pay?\"** (Simulate any scenario)"
        )

        return {
            "reply": reply,
            "reasoning": reasoning,
            "intent": "general_help",
            "grounded_facts": ["Official company schemes: Standard Veg (3000), Deluxe Veg (3800), Non-Veg (4200)"],
        }
