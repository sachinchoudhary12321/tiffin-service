"""
Main service layer for tiffin business operations.
Coordinates subscription lifecycle, pause/resume, daily dispatch, and billing.
"""

from __future__ import annotations
from datetime import date, timedelta
import re
from typing import Any, Dict, List, Optional, Set

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

