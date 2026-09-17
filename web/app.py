"""
Flask Web Dashboard for Tiffin Service Management.
Provides a modern visual interface for daily kitchen dispatch,
phone lookups, pause/resume, and monthly pro-rated billing.
"""

from __future__ import annotations
from datetime import date
import os
import sys

from flask import Flask, redirect, render_template, request, url_for

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tiffin.calendar_utils import format_date, parse_date
from tiffin.models import DayStatus
from tiffin.service import TiffinService

app = Flask(__name__, template_folder="templates")
DB_PATH = os.environ.get("TIFFIN_DB", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tiffin.db")))
service = TiffinService(DB_PATH)


@app.route("/")
def index():
    return redirect(url_for("dispatch_view"))


@app.route("/dispatch")
def dispatch_view():
    date_str = request.args.get("date")
    target_date = parse_date(date_str) if date_str else date.today()
    dispatch = service.get_daily_dispatch(target_date)
    return render_template(
        "index.html",
        active_tab="dispatch",
        dispatch=dispatch,
        today_str=format_date(date.today()),
    )


@app.route("/customers")
def customers_view():
    search_phone = request.args.get("phone", "").strip()
    dossier = None
    if search_phone:
        dossier = service.lookup_customer(search_phone)

    all_customers = service.storage.list_customers()
    plans = service.list_plans()

    return render_template(
        "index.html",
        active_tab="customers",
        search_phone=search_phone,
        dossier=dossier,
        all_customers=all_customers,
        plans=plans,
        today_str=format_date(date.today()),
        alert_msg=request.args.get("msg"),
        alert_type=request.args.get("msg_type", "success"),
    )


@app.route("/customers/subscribe", methods=["POST"])
def action_subscribe():
    name = request.form.get("name")
    phone = request.form.get("phone")
    plan_id = request.form.get("plan_id")
    address = request.form.get("address", "")
    start_date = request.form.get("start_date")
    notes = request.form.get("notes", "")

    try:
        service.subscribe(name=name, phone=phone, plan_id=plan_id, address=address, start_date=start_date, notes=notes)
        return redirect(url_for("customers_view", phone=phone, msg="Customer subscribed successfully!", msg_type="success"))
    except Exception as e:
        return redirect(url_for("customers_view", msg=f"Error subscribing: {e}", msg_type="error"))


@app.route("/customers/pause", methods=["POST"])
def action_pause():
    phone = request.form.get("phone")
    from_date = request.form.get("from_date")
    to_date = request.form.get("to_date") or None
    reason = request.form.get("reason", "")

    try:
        service.pause(phone=phone, from_date=from_date, to_date=to_date, reason=reason)
        return redirect(url_for("customers_view", phone=phone, msg="Delivery paused successfully!", msg_type="success"))
    except Exception as e:
        return redirect(url_for("customers_view", phone=phone, msg=f"Error pausing: {e}", msg_type="error"))


@app.route("/customers/resume", methods=["POST"])
def action_resume():
    phone = request.form.get("phone")
    resume_date = request.form.get("resume_date") or None

    try:
        resumed = service.resume(phone=phone, resume_date=resume_date)
        msg = "Delivery resumed successfully!" if resumed else "No active pauses to resume."
        return redirect(url_for("customers_view", phone=phone, msg=msg, msg_type="success"))
    except Exception as e:
        return redirect(url_for("customers_view", phone=phone, msg=f"Error resuming: {e}", msg_type="error"))


@app.route("/billing")
def billing_view():
    month_str = request.args.get("month")
    if not month_str:
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"

    year, month = map(int, month_str.split("-"))
    bills = service.generate_all_bills(year, month)
    grand_total = sum(b.total_amount for b in bills)

    single_phone = request.args.get("phone")
    single_bill = None
    if single_phone:
        try:
            single_bill = service.generate_bill(single_phone, year, month)
        except Exception:
            pass

    return render_template(
        "index.html",
        active_tab="billing",
        selected_month=month_str,
        year=year,
        bills=bills,
        grand_total=grand_total,
        single_bill=single_bill,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Tiffin Dashboard on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
