"""
Main service layer for tiffin business operations.
Coordinates subscription lifecycle, pause/resume, daily dispatch, and billing.
"""

from __future__ import annotations
import csv
from datetime import date, timedelta
import io
import re
from typing import Any, Dict, List, Optional, Set
import urllib.parse

from .billing import calculate_pro_rated_bill
from .calendar_utils import format_date, is_weekday, parse_date
from .models import Bill, Customer, PauseRecord, Plan, Subscription, SubscriptionStatus, User
from .storage import Storage
from werkzeug.security import generate_password_hash, check_password_hash


def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only or + prefix with digits."""
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    if not cleaned:
        raise ValueError("Phone number cannot be empty")
    return cleaned


def canonical_phone_key(phone: str) -> str:
    """Canonical 10-digit key for deduplication and duplicate detection."""
    digits = re.sub(r"[^\d]", "", phone.strip())
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


class TiffinService:
    def __init__(self, db_path: str = "tiffin.db"):
        self.storage = Storage(db_path)

    # --- Plan Management ---
    def add_plan(self, plan_id: str, name: str, monthly_price: float, description: str = "") -> Plan:
        plan = Plan(id=plan_id, name=name, monthly_price=monthly_price, description=description)
        self.storage.save_plan(plan)
        return plan

    def list_plans(self) -> List[Plan]:
        return self.storage.list_plans()

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        return self.storage.get_plan(plan_id)

    # --- User Authentication ---
    def register_user(self, username: str, password: str, email: str = "", role: str = "owner") -> User:
        username = username.strip()
        if not username:
            raise ValueError("Username cannot be empty")
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters long")
        existing = self.storage.get_user_by_username(username)
        if existing:
            raise ValueError(f"Username '{username}' already exists")
        
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            email=email.strip(),
            role=role,
        )
        return self.storage.create_user(user)

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        user = self.storage.get_user_by_username(username.strip())
        if not user:
            return None
        if check_password_hash(user.password_hash, password):
            return user
        return None

    # --- Subscription Lifecycle ---
    def subscribe(
        self,
        name: str,
        phone: str,
        plan_id: str,
        address: str = "",
        start_date: Optional[date | str] = None,
        notes: str = "",
    ) -> Subscription:
        """Subscribe a customer to a monthly weekday lunch plan."""
        phone = normalize_phone(phone)
        plan = self.storage.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan '{plan_id}' does not exist")

        s_date = parse_date(start_date) if start_date else date.today()

        customer = Customer(
            phone=phone,
            name=name.strip(),
            address=address.strip(),
            notes=notes.strip(),
        )
        self.storage.save_customer(customer)

        existing_sub = self.storage.get_subscription_for_customer(phone)
        if existing_sub and existing_sub.status != SubscriptionStatus.CANCELLED:
            # Update existing subscription
            existing_sub.plan_id = plan_id
            existing_sub.start_date = s_date
            existing_sub.status = SubscriptionStatus.ACTIVE
            self.storage.save_subscription(existing_sub)
            return existing_sub

        new_sub = Subscription(
            customer_phone=phone,
            plan_id=plan_id,
            start_date=s_date,
            status=SubscriptionStatus.ACTIVE,
        )
        new_sub.id = self.storage.save_subscription(new_sub)
        return new_sub

    def pause(
        self,
        phone: str,
        from_date: date | str,
        to_date: Optional[date | str] = None,
        reason: str = "",
    ) -> PauseRecord:
        """
        Pause deliveries for a customer.
        Can be for a fixed date range [from_date, to_date] or indefinite (to_date is None).
        """
        phone = normalize_phone(phone)
        customer = self.storage.get_customer(phone)
        if not customer:
            raise ValueError(f"Customer with phone '{phone}' not found")

        sub = self.storage.get_subscription_for_customer(phone)
        if not sub or sub.status == SubscriptionStatus.CANCELLED:
            raise ValueError(f"Customer with phone '{phone}' has no active subscription")

        f_date = parse_date(from_date)
        t_date = parse_date(to_date) if to_date else None

        if t_date is not None and t_date < f_date:
            raise ValueError(f"Pause end date ({t_date}) cannot be before start date ({f_date})")

        # Check for overlapping existing pauses
        existing_pauses = self.storage.get_pauses_for_customer(phone)
        for ep in existing_pauses:
            # Overlap test between [f_date, t_date] and [ep.start_date, ep.end_date]
            ep_end = ep.end_date or date.max
            req_end = t_date or date.max
            if max(f_date, ep.start_date) <= min(req_end, ep_end):
                raise ValueError(
                    f"Pause range [{f_date} to {t_date or 'indefinite'}] overlaps with existing pause "
                    f"[{ep.start_date} to {ep.end_date or 'indefinite'}]"
                )

        pause_rec = PauseRecord(
            customer_phone=phone,
            start_date=f_date,
            end_date=t_date,
            reason=reason.strip(),
        )
        pause_rec.id = self.storage.save_pause(pause_rec)

        today = date.today()
        if pause_rec.is_active_on(today):
            sub.status = SubscriptionStatus.PAUSED
            self.storage.save_subscription(sub)

        return pause_rec

    def resume(self, phone: str, resume_date: Optional[date | str] = None) -> bool:
        """
        Resume deliveries for a paused customer.
        If resume_date is provided, closes any active pause prior to resume_date.
        """
        phone = normalize_phone(phone)
        customer = self.storage.get_customer(phone)
        if not customer:
            raise ValueError(f"Customer with phone '{phone}' not found")

        sub = self.storage.get_subscription_for_customer(phone)
        if not sub or sub.status == SubscriptionStatus.CANCELLED:
            raise ValueError(f"Customer with phone '{phone}' has no active subscription")

        r_date = parse_date(resume_date) if resume_date else date.today()
        day_before = r_date - timedelta(days=1)

        pauses = self.storage.get_pauses_for_customer(phone)
        modified = False

        for p in pauses:
            # If indefinite pause or pause extending past or on resume_date
            if p.end_date is None or p.end_date >= r_date:
                if p.start_date >= r_date:
                    # Pause was scheduled entirely in the future after/on resume date; truncate to cancel
                    p.end_date = p.start_date - timedelta(days=1)
                else:
                    p.end_date = day_before
                self.storage.save_pause(p)
                modified = True

        today = date.today()
        if r_date <= today:
            sub.status = SubscriptionStatus.ACTIVE
            self.storage.save_subscription(sub)

        return modified

    def cancel_subscription(self, phone: str, end_date: Optional[date | str] = None) -> Subscription:
        phone = normalize_phone(phone)
        sub = self.storage.get_subscription_for_customer(phone)
        if not sub:
            raise ValueError(f"No subscription found for phone '{phone}'")
        e_date = parse_date(end_date) if end_date else date.today()
        sub.end_date = e_date
        sub.status = SubscriptionStatus.CANCELLED
        self.storage.save_subscription(sub)
        return sub

    # --- Lookups & Kitchen Dispatch ---
    def get_customer_status_on_date(self, phone: str, target: date) -> Dict[str, Any]:
        """Get live status of customer on a specific date."""
        sub = self.storage.get_subscription_for_customer(phone)
        if not sub:
            return {"status": "NO_SUBSCRIPTION", "is_delivery_day": False, "pause_reason": None}

        if target < sub.start_date:
            return {"status": "NOT_YET_STARTED", "is_delivery_day": False, "pause_reason": None}

        if sub.end_date is not None and target > sub.end_date:
            return {"status": "CANCELLED", "is_delivery_day": False, "pause_reason": None}

        if not is_weekday(target):
            return {"status": "WEEKEND", "is_delivery_day": False, "pause_reason": None}

        holidays = self.storage.get_holidays_in_month(target.year, target.month)
        if target in holidays:
            return {"status": "HOLIDAY", "is_delivery_day": False, "pause_reason": "Kitchen Holiday"}

        active_pause = self.storage.get_active_pause(phone, target)
        if active_pause:
            return {
                "status": "PAUSED",
                "is_delivery_day": False,
                "pause_reason": active_pause.reason,
                "pause_start": active_pause.start_date,
                "pause_end": active_pause.end_date,
            }

        return {"status": "ACTIVE", "is_delivery_day": True, "pause_reason": None}

    def lookup_customer(self, phone: str, as_of_date: Optional[date | str] = None) -> Dict[str, Any]:
        """
        Comprehensive phone-based lookup returning customer dossier, current status,
        pause history, plan, and month-to-date delivery metrics.
        """
        phone = normalize_phone(phone)
        customer = self.storage.get_customer(phone)
        if not customer:
            return {"found": False, "phone": phone, "error": "Customer not found"}

        check_date = parse_date(as_of_date) if as_of_date else date.today()
        sub = self.storage.get_subscription_for_customer(phone)
        plan = self.storage.get_plan(sub.plan_id) if sub else None
        pauses = self.storage.get_pauses_for_customer(phone)
        status_info = self.get_customer_status_on_date(phone, check_date)

        # Calculate current month-to-date bill estimate if active
        current_bill = None
        if sub and plan and sub.status != SubscriptionStatus.CANCELLED:
            holidays = self.storage.get_holidays_in_month(check_date.year, check_date.month)
            current_bill = calculate_pro_rated_bill(
                customer=customer,
                subscription=sub,
                plan=plan,
                pauses=pauses,
                year=check_date.year,
                month=check_date.month,
                kitchen_holidays=holidays,
            )

        return {
            "found": True,
            "customer": customer,
            "subscription": sub,
            "plan": plan,
            "pauses": pauses,
            "status_today": status_info,
            "as_of_date": check_date,
            "current_month_bill": current_bill,
        }

    def get_daily_dispatch(self, target_date: Optional[date | str] = None) -> Dict[str, Any]:
        """
        Kitchen dispatch sheet: answers 'Who is Active (cook & deliver) vs who is Paused?'
        Crucial for zero food waste and zero missed deliveries.
        """
        t_date = parse_date(target_date) if target_date else date.today()
        day_name = t_date.strftime("%A")
        is_wkday = is_weekday(t_date)

        holidays = self.storage.get_holidays_in_month(t_date.year, t_date.month)
        is_holiday = t_date in holidays

        active_deliveries: List[Dict[str, Any]] = []
        paused_deliveries: List[Dict[str, Any]] = []

        if is_wkday and not is_holiday:
            customers = self.storage.list_customers()
            for cust in customers:
                sub = self.storage.get_subscription_for_customer(cust.phone)
                if not sub or sub.status == SubscriptionStatus.CANCELLED:
                    continue

                if t_date < sub.start_date or (sub.end_date and t_date > sub.end_date):
                    continue

                plan = self.storage.get_plan(sub.plan_id)
                plan_name = plan.name if plan else sub.plan_id

                active_pause = self.storage.get_active_pause(cust.phone, t_date)
                if active_pause:
                    paused_deliveries.append({
                        "phone": cust.phone,
                        "name": cust.name,
                        "plan_name": plan_name,
                        "reason": active_pause.reason or "Paused",
                        "resume_date": active_pause.end_date or "Indefinite",
                    })
                else:
                    active_deliveries.append({
                        "phone": cust.phone,
                        "name": cust.name,
                        "plan_name": plan_name,
                        "address": cust.address,
                        "notes": cust.notes,
                    })

        # Aggregate meal plan breakdown and dietary notes
        plan_counts: Dict[str, int] = {}
        dietary_notes: List[Dict[str, str]] = []
        for item in active_deliveries:
            plan_name = item["plan_name"]
            plan_counts[plan_name] = plan_counts.get(plan_name, 0) + 1
            if item.get("notes"):
                dietary_notes.append({"name": item["name"], "phone": item["phone"], "note": item["notes"]})

        return {
            "date": t_date,
            "day_name": day_name,
            "is_weekday": is_wkday,
            "is_holiday": is_holiday,
            "active_deliveries": active_deliveries,
            "paused_deliveries": paused_deliveries,
            "active_count": len(active_deliveries),
            "paused_count": len(paused_deliveries),
            "total_subscribed": len(active_deliveries) + len(paused_deliveries),
            "plan_counts": plan_counts,
            "dietary_notes": dietary_notes,
        }

    # --- Billing Generation ---
    def generate_bill(self, phone: str, year: int, month: int) -> Bill:
        phone = normalize_phone(phone)
        customer = self.storage.get_customer(phone)
        if not customer:
            raise ValueError(f"Customer with phone '{phone}' not found")

        sub = self.storage.get_subscription_for_customer(phone)
        if not sub:
            raise ValueError(f"No subscription found for customer '{phone}'")

        plan = self.storage.get_plan(sub.plan_id)
        if not plan:
            raise ValueError(f"Plan '{sub.plan_id}' not found")

        pauses = self.storage.get_pauses_for_customer(phone)
        holidays = self.storage.get_holidays_in_month(year, month)

        return calculate_pro_rated_bill(
            customer=customer,
            subscription=sub,
            plan=plan,
            pauses=pauses,
            year=year,
            month=month,
            kitchen_holidays=holidays,
        )

    def generate_all_bills(self, year: int, month: int) -> List[Bill]:
        customers = self.storage.list_customers()
        bills: List[Bill] = []
        for cust in customers:
            sub = self.storage.get_subscription_for_customer(cust.phone)
            if not sub:
                continue
            bill = self.generate_bill(cust.phone, year, month)
            bills.append(bill)
        return bills

    def search_customers(
        self,
        query: str = "",
        sort_by: str = "name",
        order: str = "asc",
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[List[Customer], int, int]:
        return self.storage.search_customers(
            query=query,
            sort_by=sort_by,
            order=order,
            page=page,
            per_page=per_page,
        )

    def paginate_bills(
        self,
        bills: List[Bill],
        sort_by: str = "customer_name",
        order: str = "asc",
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[List[Bill], int, int]:
        reverse = (order.lower() == "desc")
        if sort_by == "total_amount":
            sorted_bills = sorted(bills, key=lambda b: b.total_amount, reverse=reverse)
        elif sort_by == "delivered_weekdays":
            sorted_bills = sorted(bills, key=lambda b: b.delivered_weekdays, reverse=reverse)
        elif sort_by == "phone":
            sorted_bills = sorted(bills, key=lambda b: b.customer_phone, reverse=reverse)
        else:
            sorted_bills = sorted(bills, key=lambda b: b.customer_name.lower(), reverse=reverse)

        total_count = len(sorted_bills)
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        offset = max(0, (page - 1) * per_page)
        paginated = sorted_bills[offset : offset + per_page]
        return paginated, total_count, total_pages

    # --- WhatsApp Messaging & CSV Exports ---
    def generate_whatsapp_message(self, bill: Bill) -> str:
        """
        Generate a formatted WhatsApp billing notification with URL encoding.
        """
        raw_msg = (
            f"🍱 *Annapurna Tiffin Service - Month-End Bill*\n"
            f"Dear {bill.customer_name},\n\n"
            f"Your pro-rated tiffin bill for *{bill.month_name} {bill.billing_year}* is ready:\n"
            f"• Plan: {bill.plan_name}\n"
            f"• Working Days: {bill.total_month_weekdays} days\n"
            f"• Meals Delivered: {bill.delivered_weekdays} days\n"
            f"• Days Paused: {bill.paused_weekdays} days (100% credited)\n"
            f"• Daily Rate: Rs. {bill.daily_rate:.2f}/meal\n"
            f"• *TOTAL AMOUNT DUE: Rs. {bill.total_amount:.2f}*\n\n"
            f"Thank you for choosing Annapurna Tiffin! 🙏"
        )
        encoded_text = urllib.parse.quote(raw_msg)
        clean_phone = re.sub(r"[^\d]", "", bill.customer_phone)
        if len(clean_phone) == 10:
            clean_phone = "91" + clean_phone  # default country code for India if 10 digits
        return f"https://wa.me/{clean_phone}?text={encoded_text}"

    def export_bills_csv(self, year: int, month: int) -> str:
        """Export monthly bills summary to CSV string."""
        bills = self.generate_all_bills(year, month)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Customer Name", "Phone", "Plan", "Month",
            "Working Weekdays", "Subscribed Days", "Paused Days",
            "Delivered Days", "Daily Rate (Rs)", "Total Bill (Rs)"
        ])
        for b in bills:
            writer.writerow([
                b.customer_name, b.customer_phone, b.plan_name, f"{year:04d}-{month:02d}",
                b.total_month_weekdays, b.subscribed_weekdays, b.paused_weekdays,
                b.delivered_weekdays, f"{b.daily_rate:.2f}", f"{b.total_amount:.2f}"
            ])
        return output.getvalue()

    def export_dispatch_csv(self, target_date: Optional[date | str] = None) -> str:
        """Export daily kitchen dispatch run-sheet to CSV string."""
        dispatch = self.get_daily_dispatch(target_date)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Delivery Status", "Customer Name", "Phone", "Plan", "Delivery Address", "Notes / Reason"
        ])
        for a in dispatch["active_deliveries"]:
            writer.writerow(["ACTIVE - DELIVER", a["name"], a["phone"], a["plan_name"], a.get("address", ""), a.get("notes", "")])
        for p in dispatch["paused_deliveries"]:
            writer.writerow(["PAUSED - SKIP", p["name"], p["phone"], p["plan_name"], "", f"Reason: {p['reason']} (Resumes: {p['resume_date']})"])
        return output.getvalue()

    # =========================================================================
    # ROUND 2 TWISTS: LEVEL 1 (T1), LEVEL 2 (T6), LEVEL 3 (T4)
    # =========================================================================

    # --- Level 1 — T1 (integrate): Notification Outbox on POST /clock ---
    def tick_clock(self, target_date: Optional[date | str] = None) -> List[Dict[str, Any]]:
        """
        Level 1 (T1): Each morning, notify the customers due a delivery today
        (active, a weekday, not paused) via the Notification Service.
        Saved to outbox and returned.
        """
        t_date = parse_date(target_date) if target_date else date.today()
        holidays = self.storage.get_holidays_in_month(t_date.year, t_date.month)

        # If weekend or holiday, no customers are due a delivery today
        if not is_weekday(t_date) or t_date in holidays:
            return []

        dispatch_data = self.get_daily_dispatch(t_date)
        active_deliveries = dispatch_data["active_deliveries"]

        notifications: List[Dict[str, Any]] = []
        for item in active_deliveries:
            recipient = item["phone"]
            cust_name = item["name"]
            plan_name = item["plan_name"]
            message = (
                f"Good morning {cust_name}! Your {plan_name} lunch delivery is on the way "
                f"for today ({format_date(t_date)})."
            )
            notif_id = self.storage.save_outbox_entry(
                recipient=recipient,
                customer_name=cust_name,
                delivery_date=format_date(t_date),
                plan_name=plan_name,
                message=message,
                status="SENT",
            )
            notifications.append({
                "id": notif_id,
                "recipient": recipient,
                "customer_name": cust_name,
                "delivery_date": format_date(t_date),
                "plan_name": plan_name,
                "message": message,
                "status": "SENT",
            })

        return notifications

    def get_outbox(self, target_date: Optional[date | str] = None) -> List[Dict[str, Any]]:
        """Retrieve dispatched notifications, optionally filtered by delivery date."""
        date_str = format_date(parse_date(target_date)) if target_date else None
        return self.storage.get_outbox(date_str)

    def clear_outbox(self) -> None:
        """Clear the outbox queue."""
        self.storage.clear_outbox()

    # --- Level 2 — T6 (lifecycle): Mid-Cycle Subscription Transfer ---
    def transfer_subscription(
        self,
        from_phone: str,
        to_phone: str,
        to_name: str,
        effective_date: date | str,
        to_address: str = "",
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Level 2 (T6): Transfer an active subscription to a new customer mid-cycle.
        The plan and billing cycle carry over, and billing splits strictly by who was served.
        """
        from_phone = normalize_phone(from_phone)
        to_phone = normalize_phone(to_phone)
        if from_phone == to_phone:
            raise ValueError("Cannot transfer subscription to the same phone number")

        eff_date = parse_date(effective_date)
        from_sub = self.storage.get_subscription_for_customer(from_phone)
        if not from_sub:
            raise ValueError(f"No active subscription found for customer '{from_phone}'")

        if eff_date < from_sub.start_date:
            raise ValueError("Transfer effective date cannot be before subscription start date")

        # 1. Terminate original subscription on the day before transfer effective date
        from_sub.end_date = eff_date - timedelta(days=1)
        self.storage.save_subscription(from_sub)

        # 2. Register or update the transferee customer
        to_cust = self.storage.get_customer(to_phone)
        if not to_cust:
            to_cust = Customer(
                phone=to_phone,
                name=to_name.strip() if to_name else f"Customer {to_phone[-4:]}",
                address=to_address.strip(),
                notes=notes.strip(),
            )
            self.storage.save_customer(to_cust)

        # 3. Create new subscription for transferee starting exactly on effective_date
        to_sub = Subscription(
            customer_phone=to_phone,
            plan_id=from_sub.plan_id,
            start_date=eff_date,
            status=SubscriptionStatus.ACTIVE,
        )
        self.storage.save_subscription(to_sub)

        # 4. Record the transfer audit record
        transfer_id = self.storage.record_transfer(
            from_phone=from_phone,
            to_phone=to_phone,
            plan_id=from_sub.plan_id,
            cycle_year=eff_date.year,
            cycle_month=eff_date.month,
            effective_date=format_date(eff_date),
            notes=notes,
        )

        plan = self.storage.get_plan(from_sub.plan_id)
        plan_name = plan.name if plan else from_sub.plan_id

        return {
            "success": True,
            "transfer_id": transfer_id,
            "from_phone": from_phone,
            "to_phone": to_phone,
            "to_name": to_cust.name,
            "plan_id": from_sub.plan_id,
            "plan_name": plan_name,
            "effective_date": format_date(eff_date),
            "cycle": f"{eff_date.year:04d}-{eff_date.month:02d}",
            "message": f"Subscription for {plan_name} transferred from {from_phone} to {to_cust.name} ({to_phone}) effective {format_date(eff_date)}. Billing splits by who was served.",
        }

    def list_transfers(self, year: Optional[int] = None, month: Optional[int] = None) -> List[Dict[str, Any]]:
        """List mid-cycle subscription transfers."""
        return self.storage.get_transfers(year, month)

    # --- Level 3 — T4 (messy data): Ingest Messy Customer List ---
    def import_messy_customers(self, raw_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Level 3 (T4): Import a messy customer list (duplicate phones, mixed date formats, blanks)
        into clean subscriptions with an { imported, deduped, rejected } report.
        """
        from .calendar_utils import parse_flexible_date

        imported: List[Dict[str, Any]] = []
        deduped: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        seen_batch_keys: Set[str] = set()
        available_plans = {p.id: p for p in self.storage.list_plans()}
        default_plan_id = "standard_veg" if "standard_veg" in available_plans else list(available_plans.keys())[0]

        for idx, row in enumerate(raw_records, start=1):
            raw_phone = str(row.get("phone") or row.get("mobile") or row.get("contact") or "").strip()
            raw_name = str(row.get("name") or row.get("customer_name") or "").strip()
            raw_date = row.get("start_date") or row.get("date") or row.get("joining_date")
            raw_plan = str(row.get("plan_id") or row.get("plan") or "").strip()
            address = str(row.get("address") or "").strip()
            notes = str(row.get("notes") or "").strip()

            # 1. Validation: Missing Name
            if not raw_name:
                rejected.append({
                    "row": idx,
                    "raw": row,
                    "reason": "Missing customer name (blank field)",
                })
                continue

            # 2. Validation: Phone number digits
            digits_only = re.sub(r"[^\d]", "", raw_phone)
            if len(digits_only) < 8:
                rejected.append({
                    "row": idx,
                    "raw": row,
                    "reason": f"Invalid or missing phone number: '{raw_phone}' (less than 8 valid digits)",
                })
                continue

            phone_cleaned = re.sub(r"[^\d+]", "", raw_phone)
            try:
                normalized_phone = normalize_phone(phone_cleaned)
            except Exception as e:
                rejected.append({
                    "row": idx,
                    "raw": row,
                    "reason": f"Failed to normalize phone: {str(e)}",
                })
                continue

            phone_canon = canonical_phone_key(phone_cleaned)

            # 3. Validation: Date parsing with multi-format support
            parsed_date = parse_flexible_date(raw_date) if raw_date else date.today()
            if raw_date and parsed_date is None:
                rejected.append({
                    "row": idx,
                    "raw": row,
                    "reason": f"Unparseable date format: '{raw_date}'",
                })
                continue

            # 4. Validation: Plan Resolution
            plan_id = raw_plan if raw_plan in available_plans else default_plan_id

            # 5. Deduplication: In-batch duplicates
            if phone_canon in seen_batch_keys:
                deduped.append({
                    "row": idx,
                    "phone": normalized_phone,
                    "name": raw_name,
                    "reason": "Duplicate phone number encountered in current import batch (skipped duplicate)",
                })
                continue

            # 6. Deduplication: Existing active subscription in database
            existing_sub = self.storage.get_subscription_for_customer(normalized_phone)
            if not existing_sub:
                for c in self.storage.list_customers():
                    if canonical_phone_key(c.phone) == phone_canon:
                        existing_sub = self.storage.get_subscription_for_customer(c.phone)
                        if existing_sub:
                            break

            if existing_sub and existing_sub.status == SubscriptionStatus.ACTIVE:
                deduped.append({
                    "row": idx,
                    "phone": normalized_phone,
                    "name": raw_name,
                    "reason": f"Customer already has an active subscription in database (Plan: '{existing_sub.plan_id}')",
                })
                seen_batch_keys.add(phone_canon)
                continue

            # 7. Creation of clean subscriber
            try:
                self.subscribe(
                    name=raw_name,
                    phone=normalized_phone,
                    plan_id=plan_id,
                    address=address,
                    start_date=parsed_date,
                    notes=notes,
                )
                seen_batch_keys.add(phone_canon)
                imported.append({
                    "row": idx,
                    "phone": normalized_phone,
                    "name": raw_name,
                    "plan_id": plan_id,
                    "plan_name": available_plans[plan_id].name if plan_id in available_plans else plan_id,
                    "start_date": format_date(parsed_date),
                })
            except Exception as err:
                rejected.append({
                    "row": idx,
                    "raw": row,
                    "reason": f"Database insertion error: {str(err)}",
                })

        return {
            "success": True,
            "imported": imported,
            "deduped": deduped,
            "rejected": rejected,
            "summary": {
                "total_rows": len(raw_records),
                "imported_count": len(imported),
                "deduped_count": len(deduped),
                "rejected_count": len(rejected),
            },
        }


