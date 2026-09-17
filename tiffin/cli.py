"""
Command-Line Interface for Tiffin Service Owners.
Provides quick phone lookups, subscription management, pause/resume,
daily kitchen dispatch sheets, and monthly billing statements.
"""

from __future__ import annotations
import argparse
from datetime import date, datetime
import sys
from typing import Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .calendar_utils import format_date, parse_date
from .models import DayStatus
from .service import TiffinService


CURRENCY = "Rs. "


def print_banner():
    print("=" * 65)
    print("      TIFFIN SERVICE MANAGEMENT & PRO-RATED BILLING SYSTEM      ")
    print("=" * 65)


def cmd_plans(service: TiffinService, args):
    plans = service.list_plans()
    print("\n--- AVAILABLE TIFFIN PLANS ---")
    print(f"{'Plan ID':<16} | {'Plan Name':<22} | {'Monthly Price':<14} | {'Description'}")
    print("-" * 75)
    for p in plans:
        print(f"{p.id:<16} | {p.name:<22} | {CURRENCY}{p.monthly_price:<10.2f} | {p.description}")
    print("-" * 75)


def cmd_subscribe(service: TiffinService, args):
    try:
        sub = service.subscribe(
            name=args.name,
            phone=args.phone,
            plan_id=args.plan,
            address=args.address or "",
            start_date=args.start_date,
            notes=args.notes or "",
        )
        plan = service.get_plan(sub.plan_id)
        plan_name = plan.name if plan else sub.plan_id
        price = plan.monthly_price if plan else 0.0

        print("\n[SUCCESS] Customer Subscribed Successfully!")
        print(f"  Name:        {args.name}")
        print(f"  Phone:       {sub.customer_phone}")
        print(f"  Plan:        {plan_name} ({CURRENCY}{price:.2f}/month)")
        print(f"  Start Date:  {format_date(sub.start_date)}")
        print(f"  Status:      {sub.status.value}")
        if args.address:
            print(f"  Address:     {args.address}")
    except Exception as e:
        print(f"\n[ERROR] Error subscribing customer: {e}")


def cmd_pause(service: TiffinService, args):
    try:
        pause_rec = service.pause(
            phone=args.phone,
            from_date=args.from_date,
            to_date=args.to_date,
            reason=args.reason or "",
        )
        print("\n[PAUSED] Delivery Paused Successfully!")
        print(f"  Phone:      {pause_rec.customer_phone}")
        print(f"  From Date:  {format_date(pause_rec.start_date)}")
        print(f"  To Date:    {format_date(pause_rec.end_date) if pause_rec.end_date else 'Indefinite (until resumed)'}")
        if pause_rec.reason:
            print(f"  Reason:     {pause_rec.reason}")
    except Exception as e:
        print(f"\n[ERROR] Error pausing delivery: {e}")


def cmd_resume(service: TiffinService, args):
    try:
        resumed = service.resume(phone=args.phone, resume_date=args.date)
        if resumed:
            print(f"\n[RESUMED] Delivery Resumed Successfully for {args.phone} (effective: {args.date or 'today'})")
        else:
            print(f"\n[INFO] No open pauses found to resume for {args.phone}.")
    except Exception as e:
        print(f"\n[ERROR] Error resuming delivery: {e}")


def cmd_lookup(service: TiffinService, args):
    result = service.lookup_customer(args.phone, as_of_date=args.date)
    if not result["found"]:
        print(f"\n[NOT FOUND] {result['error']} (Phone: {args.phone})")
        return

    c = result["customer"]
    sub = result["subscription"]
    plan = result["plan"]
    st = result["status_today"]
    bill = result["current_month_bill"]

    print("\n" + "=" * 55)
    print(f"CUSTOMER PROFILE: {c.name.upper()}")
    print("=" * 55)
    print(f"  Phone:           {c.phone}")
    print(f"  Delivery Addr:   {c.address or 'N/A'}")
    if c.notes:
        print(f"  Dietary/Notes:   {c.notes}")
    
    if sub and plan:
        print(f"  Current Plan:    {plan.name} ({CURRENCY}{plan.monthly_price:.2f}/month)")
        print(f"  Subscribed On:   {format_date(sub.start_date)}")
        
        status_label = st["status"]
        if status_label == "ACTIVE":
            status_display = "[ACTIVE] Delivery Scheduled"
        elif status_label == "PAUSED":
            status_display = f"[PAUSED] ({st['pause_reason'] or 'Customer paused'})"
        elif status_label == "WEEKEND":
            status_display = "[WEEKEND] (No Delivery)"
        else:
            status_display = f"[{status_label}]"
        print(f"  Status Today:    {status_display}")

        if st["status"] == "PAUSED":
            end_s = format_date(st["pause_end"]) if st["pause_end"] else "Indefinite"
            print(f"  Pause Window:    {format_date(st['pause_start'])} to {end_s}")

        if bill:
            print("-" * 55)
            print(f"  CURRENT MONTH ({bill.month_name} {bill.billing_year}) METRICS:")
            print(f"    Total Weekdays in Month: {bill.total_month_weekdays}")
            print(f"    Subscribed Weekdays:     {bill.subscribed_weekdays}")
            print(f"    Paused Weekdays:         {bill.paused_weekdays}")
            print(f"    Delivered Weekdays:      {bill.delivered_weekdays}")
            print(f"    Daily Rate:              {CURRENCY}{bill.daily_rate:.2f}/meal")
            print(f"    Estimated Current Bill:  {CURRENCY}{bill.total_amount:.2f}")
    else:
        print("  Subscription:    No active subscription")
    print("=" * 55)


def cmd_dispatch(service: TiffinService, args):
    target = parse_date(args.date) if args.date else date.today()
    dispatch = service.get_daily_dispatch(target)

    print("\n" + "=" * 65)
    print(f"KITCHEN DISPATCH SHEET: {dispatch['day_name'].upper()}, {format_date(target)}")
    print("=" * 65)

    if not dispatch["is_weekday"]:
        print("\n  [WEEKEND NOTICE] Kitchen closed on weekends (Mon-Fri service only).\n")
        return

    if dispatch["is_holiday"]:
        print("\n  [HOLIDAY NOTICE] Kitchen closed for scheduled holiday.\n")
        return

    print(f"  TOTAL SUBSCRIBED: {dispatch['total_subscribed']}")
    print(f"  ACTIVE TO COOK & DELIVER: {dispatch['active_count']} tiffins")
    print(f"  PAUSED (DO NOT PACK):     {dispatch['paused_count']} tiffins")
    print("-" * 65)

    print("\n[ACTIVE DELIVERIES TO PREPARE]:")
    if dispatch["active_deliveries"]:
        for idx, item in enumerate(dispatch["active_deliveries"], 1):
            addr = f" - {item['address']}" if item['address'] else ""
            notes = f" [{item['notes']}]" if item['notes'] else ""
            print(f"  {idx}. {item['name']} ({item['phone']}) - {item['plan_name']}{addr}{notes}")
    else:
        print("  None.")

    print("\n[PAUSED CUSTOMERS (DO NOT COOK/DISPATCH)]:")
    if dispatch["paused_deliveries"]:
        for idx, item in enumerate(dispatch["paused_deliveries"], 1):
            resume = format_date(item["resume_date"]) if isinstance(item["resume_date"], date) else item["resume_date"]
            print(f"  {idx}. {item['name']} ({item['phone']}) - Reason: {item['reason']} (Resumes: {resume})")
    else:
        print("  None.")
    print("=" * 65)


def cmd_bill(service: TiffinService, args):
    parts = args.month.split("-")
    if len(parts) != 2:
        print("[ERROR] Invalid month format. Use YYYY-MM (e.g. 2026-10)")
        return
    year, month = int(parts[0]), int(parts[1])

    try:
        bill = service.generate_bill(args.phone, year, month)
        print("\n" + "=" * 65)
        print(f"MONTH-END TIFFIN BILL: {bill.month_name.upper()} {bill.billing_year}")
        print("=" * 65)
        print(f"  Customer Name:         {bill.customer_name}")
        print(f"  Phone:                 {bill.customer_phone}")
        print(f"  Plan:                  {bill.plan_name} ({CURRENCY}{bill.plan_monthly_price:.2f}/mo)")
        print(f"  Total Month Weekdays:  {bill.total_month_weekdays} days")
        print(f"  Days Subscribed:       {bill.subscribed_weekdays} days")
        print(f"  Days Paused:           {bill.paused_weekdays} days")
        print(f"  Days Delivered:        {bill.delivered_weekdays} days")
        print(f"  Calculated Daily Rate: {CURRENCY}{bill.daily_rate:.2f} / delivery")
        print("-" * 65)
        print(f"  TOTAL AMOUNT DUE:      {CURRENCY}{bill.total_amount:.2f}")
        print("=" * 65)

        if getattr(args, "itemized", False) or getattr(args, "verbose", False):
            print("\n  ITEMIZED DELIVERY CALENDAR AUDIT:")
            print(f"  {'Date':<12} | {'Day':<10} | {'Status':<16} | {'Notes'}")
            print("  " + "-" * 60)
            for d in bill.days_breakdown:
                if d.status == DayStatus.WEEKEND:
                    continue
                print(f"  {format_date(d.date):<12} | {d.day_name:<10} | {d.status.value:<16} | {d.note}")
            print("  " + "-" * 60)
    except Exception as e:
        print(f"\n[ERROR] Error generating bill: {e}")


def cmd_bills(service: TiffinService, args):
    parts = args.month.split("-")
    if len(parts) != 2:
        print("[ERROR] Invalid month format. Use YYYY-MM (e.g. 2026-10)")
        return
    year, month = int(parts[0]), int(parts[1])

    bills = service.generate_all_bills(year, month)
    print("\n" + "=" * 80)
    month_str = bills[0].month_name if bills else month
    print(f"ALL CUSTOMERS BILLING SUMMARY - {month_str} {year}")
    print("=" * 80)
    print(f"{'Customer':<18} | {'Phone':<12} | {'Plan':<16} | {'Delivered':<10} | {'Paused':<8} | {'Total Bill'}")
    print("-" * 80)
    grand_total = 0.0
    for b in bills:
        grand_total += b.total_amount
        print(f"{b.customer_name[:18]:<18} | {b.customer_phone:<12} | {b.plan_name[:16]:<16} | {b.delivered_weekdays:>4}/{b.total_month_weekdays:<4} | {b.paused_weekdays:>3} days | {CURRENCY}{b.total_amount:>8.2f}")
    print("-" * 80)
    print(f"{'GRAND TOTAL':<60} | {CURRENCY}{grand_total:>8.2f}")
    print("=" * 80)


def cmd_interactive(service: TiffinService):
    while True:
        print("\n" + "=" * 50)
        print("       TIFFIN OWNER CONTROL MENU")
        print("=" * 50)
        print("  1. View Today's Kitchen Dispatch (Active vs Paused)")
        print("  2. Look up Customer by Phone")
        print("  3. Pause a Customer's Deliveries")
        print("  4. Resume a Customer's Deliveries")
        print("  5. Subscribe New Customer")
        print("  6. Generate Customer Month-End Bill")
        print("  7. Generate All Customers Billing Summary")
        print("  8. View Available Plans")
        print("  0. Exit")
        print("-" * 50)
        choice = input("Enter choice (0-8): ").strip()

        if choice == "0":
            print("Exiting. Have a great day!")
            break
        elif choice == "1":
            target_str = input("Enter date (YYYY-MM-DD, or press Enter for today): ").strip()
            class Args:
                date = target_str or None
            cmd_dispatch(service, Args())
        elif choice == "2":
            ph = input("Enter customer phone number: ").strip()
            class Args:
                phone = ph
                date = None
            cmd_lookup(service, Args())
        elif choice == "3":
            ph = input("Enter customer phone number: ").strip()
            f_date = input("Pause from date (YYYY-MM-DD): ").strip()
            t_date = input("Pause to date (YYYY-MM-DD, or Enter for indefinite): ").strip() or None
            reason = input("Reason (optional): ").strip()
            class Args:
                phone = ph
                from_date = f_date
                to_date = t_date
                reason = reason
            cmd_pause(service, Args())
        elif choice == "4":
            ph = input("Enter customer phone number: ").strip()
            r_date = input("Resume date (YYYY-MM-DD, or Enter for today): ").strip() or None
            class Args:
                phone = ph
                date = r_date
            cmd_resume(service, Args())
        elif choice == "5":
            name = input("Customer name: ").strip()
            ph = input("Customer phone: ").strip()
            cmd_plans(service, None)
            plan = input("Plan ID (e.g., standard_veg, special_veg, non_veg): ").strip()
            addr = input("Delivery address: ").strip()
            s_date = input("Start date (YYYY-MM-DD, or Enter for today): ").strip() or None
            notes = input("Dietary preferences / notes: ").strip()
            class Args:
                pass
            args = Args()
            args.name = name
            args.phone = ph
            args.plan = plan
            args.address = addr
            args.start_date = s_date
            args.notes = notes
            cmd_subscribe(service, args)
        elif choice == "6":
            ph = input("Enter customer phone: ").strip()
            m = input("Billing month (YYYY-MM, e.g. 2026-10): ").strip()
            itemized = input("Show full daily itemized audit? (y/n): ").strip().lower() == "y"
            class Args:
                phone = ph
                month = m
                verbose = False
                itemized = itemized
            cmd_bill(service, args=Args())
        elif choice == "7":
            m = input("Billing month (YYYY-MM, e.g. 2026-10): ").strip()
            class Args:
                month = m
            cmd_bills(service, Args())
        elif choice == "8":
            cmd_plans(service, None)


def main():
    parser = argparse.ArgumentParser(description="Tiffin Service Manager & Pro-Rated Billing CLI")
    parser.add_argument("--db", default="tiffin.db", help="Path to SQLite database file")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Plans
    subparsers.add_parser("plans", help="List available tiffin plans")

    # Subscribe
    sub_parser = subparsers.add_parser("subscribe", help="Subscribe a customer")
    sub_parser.add_argument("--name", required=True, help="Customer name")
    sub_parser.add_argument("--phone", required=True, help="Customer phone number")
    sub_parser.add_argument("--plan", required=True, help="Plan ID")
    sub_parser.add_argument("--address", help="Delivery address")
    sub_parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    sub_parser.add_argument("--notes", help="Special notes")

    # Pause
    pause_parser = subparsers.add_parser("pause", help="Pause delivery for a customer")
    pause_parser.add_argument("--phone", required=True, help="Customer phone number")
    pause_parser.add_argument("--from", dest="from_date", required=True, help="Start date of pause (YYYY-MM-DD)")
    pause_parser.add_argument("--to", dest="to_date", help="End date of pause (YYYY-MM-DD, omit for indefinite)")
    pause_parser.add_argument("--reason", help="Reason for pause")

    # Resume
    resume_parser = subparsers.add_parser("resume", help="Resume delivery for a customer")
    resume_parser.add_argument("--phone", required=True, help="Customer phone number")
    resume_parser.add_argument("--date", help="Effective resume date (YYYY-MM-DD, defaults to today)")

    # Lookup
    lookup_parser = subparsers.add_parser("lookup", help="Look up customer by phone")
    lookup_parser.add_argument("phone", help="Customer phone number")
    lookup_parser.add_argument("--date", help="As-of date (YYYY-MM-DD, defaults to today)")

    # Dispatch
    dispatch_parser = subparsers.add_parser("dispatch", help="View kitchen dispatch sheet (Active vs Paused)")
    dispatch_parser.add_argument("--date", help="Target date (YYYY-MM-DD, defaults to today)")

    # Bill
    bill_parser = subparsers.add_parser("bill", help="Generate pro-rated bill for a customer")
    bill_parser.add_argument("--phone", required=True, help="Customer phone number")
    bill_parser.add_argument("--month", required=True, help="Billing month (YYYY-MM)")
    bill_parser.add_argument("--itemized", action="store_true", help="Print day-by-day itemized audit breakdown")

    # Bills (all)
    bills_parser = subparsers.add_parser("bills", help="Generate billing summary for all customers")
    bills_parser.add_argument("--month", required=True, help="Billing month (YYYY-MM)")

    # Interactive
    subparsers.add_parser("interactive", help="Launch interactive owner control panel")

    args = parser.parse_args()
    service = TiffinService(args.db)

    if args.command == "plans":
        cmd_plans(service, args)
    elif args.command == "subscribe":
        cmd_subscribe(service, args)
    elif args.command == "pause":
        cmd_pause(service, args)
    elif args.command == "resume":
        cmd_resume(service, args)
    elif args.command == "lookup":
        cmd_lookup(service, args)
    elif args.command == "dispatch":
        cmd_dispatch(service, args)
    elif args.command == "bill":
        cmd_bill(service, args)
    elif args.command == "bills":
        cmd_bills(service, args)
    elif args.command == "interactive":
        cmd_interactive(service)
    else:
        print_banner()
        parser.print_help()


if __name__ == "__main__":
    main()
