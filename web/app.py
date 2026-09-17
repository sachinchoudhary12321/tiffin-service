"""
Flask Web Dashboard & REST API for Tiffin Service Management.
Includes User Authentication, Search, Pagination, Sorting,
Daily Kitchen Dispatch, and Pro-Rated Month-End Billing.
"""

from __future__ import annotations
from datetime import date
from functools import wraps
import os
import sys

from flask import Flask, flash, jsonify, redirect, render_template, request, Response, session, url_for

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tiffin.calendar_utils import format_date, parse_date
from tiffin.chatbot import TiffinChatbot
from tiffin.models import DayStatus
from tiffin.service import TiffinService

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "tiffin-auriga-secret-key-2026")

DB_PATH = os.environ.get("TIFFIN_DB", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tiffin.db")))
service = TiffinService(DB_PATH)
chatbot = TiffinChatbot(service)


def get_current_user():
    user_id = session.get("user_id")
    if user_id:
        return service.storage.get_user_by_id(user_id)
    return None


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not get_current_user():
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login_view", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# WEB UI ROUTES
# ==========================================

@app.route("/")
def landing_view():
    """One-page product landing page."""
    current_user = get_current_user()
    return render_template("landing.html", current_user=current_user)


@app.route("/login", methods=["GET", "POST"])
def login_view():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = service.authenticate_user(username, password)
        if user:
            session["user_id"] = user.id
            session["username"] = user.username
            flash(f"Welcome back, {user.username}!", "success")
            next_url = request.args.get("next") or url_for("dispatch_view")
            return redirect(next_url)
        else:
            flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register_view():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        email = request.form.get("email", "").strip()
        try:
            user = service.register_user(username, password, email)
            session["user_id"] = user.id
            session["username"] = user.username
            flash("Account registered successfully!", "success")
            return redirect(url_for("dispatch_view"))
        except Exception as e:
            flash(str(e), "error")
    return render_template("register.html")


@app.route("/logout")
def logout_view():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("landing_view"))


@app.route("/dispatch")
def dispatch_view():
    date_str = request.args.get("date")
    target_date = parse_date(date_str) if date_str else date.today()
    dispatch = service.get_daily_dispatch(target_date)
    return render_template(
        "dispatch.html",
        active_tab="dispatch",
        dispatch=dispatch,
        today_str=format_date(date.today()),
        current_user=get_current_user(),
    )


@app.route("/customers")
def customers_view():
    query = request.args.get("query", "").strip()
    sort_by = request.args.get("sort_by", "name")
    order = request.args.get("order", "asc")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 8))

    search_phone = request.args.get("phone", "").strip()
    dossier = None
    if search_phone:
        dossier = service.lookup_customer(search_phone)

    customers, total_count, total_pages = service.search_customers(
        query=query, sort_by=sort_by, order=order, page=page, per_page=per_page
    )
    plans = service.list_plans()

    return render_template(
        "customers.html",
        active_tab="customers",
        query=query,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
        customers=customers,
        search_phone=search_phone,
        dossier=dossier,
        plans=plans,
        today_str=format_date(date.today()),
        current_user=get_current_user(),
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
        flash("Customer subscribed successfully!", "success")
        return redirect(url_for("customers_view", phone=phone))
    except Exception as e:
        flash(f"Error subscribing: {e}", "error")
        return redirect(url_for("customers_view"))


@app.route("/customers/pause", methods=["POST"])
def action_pause():
    phone = request.form.get("phone")
    from_date = request.form.get("from_date")
    to_date = request.form.get("to_date") or None
    reason = request.form.get("reason", "")

    try:
        service.pause(phone=phone, from_date=from_date, to_date=to_date, reason=reason)
        flash("Delivery paused successfully!", "success")
        return redirect(url_for("customers_view", phone=phone))
    except Exception as e:
        flash(f"Error pausing: {e}", "error")
        return redirect(url_for("customers_view", phone=phone))


@app.route("/customers/resume", methods=["POST"])
def action_resume():
    phone = request.form.get("phone")
    resume_date = request.form.get("resume_date") or None

    try:
        resumed = service.resume(phone=phone, resume_date=resume_date)
        msg = "Delivery resumed successfully!" if resumed else "No active pauses found to resume."
        flash(msg, "success")
        return redirect(url_for("customers_view", phone=phone))
    except Exception as e:
        flash(f"Error resuming: {e}", "error")
        return redirect(url_for("customers_view", phone=phone))


@app.route("/customers/transfer", methods=["POST"])
def action_transfer():
    from_phone = request.form.get("from_phone", "").strip()
    to_phone = request.form.get("to_phone", "").strip()
    to_name = request.form.get("to_name", "").strip()
    to_address = request.form.get("to_address", "").strip()
    effective_date = request.form.get("effective_date", "").strip()
    notes = request.form.get("notes", "").strip()

    try:
        res = service.transfer_subscription(
            from_phone=from_phone,
            to_phone=to_phone,
            to_name=to_name,
            effective_date=effective_date,
            to_address=to_address,
            notes=notes,
        )
        flash(res["message"], "success")
        return redirect(url_for("customers_view", phone=to_phone))
    except Exception as e:
        flash(f"Error transferring subscription: {e}", "error")
        return redirect(url_for("customers_view", phone=from_phone))


@app.route("/customers/import", methods=["POST"])
def action_import():
    records = []
    if "file" in request.files:
        uploaded_file = request.files["file"]
        if uploaded_file and uploaded_file.filename:
            content = uploaded_file.stream.read().decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                records.append({k.strip().lower(): v.strip() for k, v in row.items() if k})
    elif request.form.get("raw_data"):
        raw_text = request.form.get("raw_data", "").strip()
        if raw_text.startswith("["):
            import json
            records = json.loads(raw_text)
        else:
            reader = csv.DictReader(io.StringIO(raw_text))
            for row in reader:
                records.append({k.strip().lower(): v.strip() for k, v in row.items() if k})

    if not records:
        flash("No valid records found to import. Provide CSV file or text.", "error")
        return redirect(url_for("customers_view"))

    try:
        report = service.import_messy_customers(records)
        summary = report["summary"]
        flash(f"Import Report: {summary['imported_count']} imported, {summary['deduped_count']} deduped, {summary['rejected_count']} rejected.", "info")
        return redirect(url_for("customers_view"))
    except Exception as e:
        flash(f"Error during import: {e}", "error")
        return redirect(url_for("customers_view"))


@app.route("/billing")
def billing_view():
    month_str = request.args.get("month")
    if not month_str:
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"

    year, month = map(int, month_str.split("-"))
    all_bills = service.generate_all_bills(year, month)
    grand_total = sum(b.total_amount for b in all_bills)

    sort_by = request.args.get("sort_by", "customer_name")
    order = request.args.get("order", "asc")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 8))

    paginated_bills, total_count, total_pages = service.paginate_bills(
        all_bills, sort_by=sort_by, order=order, page=page, per_page=per_page
    )

    single_phone = request.args.get("phone")
    single_bill = None
    whatsapp_link = None
    if single_phone:
        try:
            single_bill = service.generate_bill(single_phone, year, month)
            whatsapp_link = service.generate_whatsapp_message(single_bill)
        except Exception:
            pass

    return render_template(
        "billing.html",
        active_tab="billing",
        selected_month=month_str,
        year=year,
        bills=paginated_bills,
        total_count=total_count,
        total_pages=total_pages,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        order=order,
        grand_total=grand_total,
        single_bill=single_bill,
        whatsapp_link=whatsapp_link,
        current_user=get_current_user(),
    )


@app.route("/my-bill")
def my_bill_view():
    """Public customer self-service portal: look up your own live bill by phone."""
    phone = request.args.get("phone", "").strip()
    month_str = request.args.get("month")
    if not month_str:
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"

    year, month = map(int, month_str.split("-"))
    bill = None
    error = None

    if phone:
        try:
            bill = service.generate_bill(phone, year, month)
        except Exception as e:
            error = str(e)

    return render_template(
        "my_bill.html",
        phone=phone,
        month=month_str,
        bill=bill,
        error=error,
        current_user=get_current_user(),
    )


@app.route("/assistant")
def assistant_view():
    """Interactive Zero-Hallucination AI Assistant view."""
    current_user = get_current_user()
    return render_template("assistant.html", current_user=current_user)


@app.route("/export/bills.csv")
def export_bills():
    month_str = request.args.get("month")
    if not month_str:
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"
    year, month = map(int, month_str.split("-"))
    csv_data = service.export_bills_csv(year, month)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=tiffin_bills_{year:04d}_{month:02d}.csv"}
    )


@app.route("/export/dispatch.csv")
def export_dispatch():
    date_str = request.args.get("date")
    target_date = parse_date(date_str) if date_str else date.today()
    csv_data = service.export_dispatch_csv(target_date)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=kitchen_dispatch_{format_date(target_date)}.csv"}
    )



# ==========================================
# REST API ENDPOINTS (JSON)
# ==========================================

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    email = data.get("email", "").strip()
    try:
        user = service.register_user(username, password, email)
        return jsonify({
            "success": True,
            "message": "User registered successfully",
            "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role},
        }), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    user = service.authenticate_user(username, password)
    if user:
        session["user_id"] = user.id
        session["username"] = user.username
        return jsonify({
            "success": True,
            "message": "Login successful",
            "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role},
        }), 200
    return jsonify({"success": False, "error": "Invalid username or password"}), 401


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"}), 200


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "authenticated": False}), 401
    return jsonify({
        "success": True,
        "authenticated": True,
        "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role},
    }), 200


@app.route("/api/plans", methods=["GET"])
def api_plans():
    plans = service.list_plans()
    return jsonify({
        "success": True,
        "plans": [
            {"id": p.id, "name": p.name, "monthly_price": p.monthly_price, "description": p.description}
            for p in plans
        ],
    }), 200


@app.route("/api/customers", methods=["GET"])
def api_customers():
    query = request.args.get("query", "").strip()
    sort_by = request.args.get("sort_by", "name")
    order = request.args.get("order", "asc")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10))

    customers, total_count, total_pages = service.search_customers(
        query=query, sort_by=sort_by, order=order, page=page, per_page=per_page
    )
    return jsonify({
        "success": True,
        "query": query,
        "sort_by": sort_by,
        "order": order,
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "customers": [
            {"phone": c.phone, "name": c.name, "address": c.address, "notes": c.notes, "created_at": c.created_at}
            for c in customers
        ],
    }), 200


@app.route("/api/customers/<phone>", methods=["GET"])
def api_customer_dossier(phone):
    as_of = request.args.get("date")
    result = service.lookup_customer(phone, as_of_date=as_of)
    if not result["found"]:
        return jsonify({"success": False, "error": "Customer not found"}), 404

    c = result["customer"]
    sub = result["subscription"]
    plan = result["plan"]
    st = result["status_today"]
    bill = result["current_month_bill"]

    return jsonify({
        "success": True,
        "customer": {"phone": c.phone, "name": c.name, "address": c.address, "notes": c.notes},
        "subscription": {
            "plan_id": sub.plan_id if sub else None,
            "start_date": format_date(sub.start_date) if sub else None,
            "status": sub.status.value if sub else None,
        } if sub else None,
        "plan": {
            "id": plan.id, "name": plan.name, "monthly_price": plan.monthly_price
        } if plan else None,
        "status_today": {
            "status": st["status"],
            "is_delivery_day": st["is_delivery_day"],
            "pause_reason": st["pause_reason"],
        },
        "current_month_estimate": {
            "month": bill.month_name if bill else None,
            "delivered_weekdays": bill.delivered_weekdays if bill else None,
            "paused_weekdays": bill.paused_weekdays if bill else None,
            "total_amount": bill.total_amount if bill else None,
        } if bill else None,
    }), 200


@app.route("/api/subscriptions", methods=["POST"])
def api_subscribe():
    data = request.get_json() or {}
    try:
        sub = service.subscribe(
            name=data["name"],
            phone=data["phone"],
            plan_id=data["plan_id"],
            address=data.get("address", ""),
            start_date=data.get("start_date"),
            notes=data.get("notes", ""),
        )
        return jsonify({
            "success": True,
            "message": "Subscription created successfully",
            "subscription": {
                "phone": sub.customer_phone,
                "plan_id": sub.plan_id,
                "start_date": format_date(sub.start_date),
                "status": sub.status.value,
            },
        }), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/pauses", methods=["POST"])
def api_pause():
    data = request.get_json() or {}
    try:
        p = service.pause(
            phone=data["phone"],
            from_date=data["from_date"],
            to_date=data.get("to_date"),
            reason=data.get("reason", ""),
        )
        return jsonify({
            "success": True,
            "message": "Delivery paused successfully",
            "pause": {
                "id": p.id,
                "phone": p.customer_phone,
                "from_date": format_date(p.start_date),
                "to_date": format_date(p.end_date) if p.end_date else None,
                "reason": p.reason,
            },
        }), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/resumes", methods=["POST"])
def api_resume():
    data = request.get_json() or {}
    try:
        resumed = service.resume(phone=data["phone"], resume_date=data.get("resume_date"))
        return jsonify({"success": True, "resumed": resumed}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/dispatch", methods=["GET"])
def api_dispatch():
    date_str = request.args.get("date")
    target_date = parse_date(date_str) if date_str else date.today()
    dispatch = service.get_daily_dispatch(target_date)
    return jsonify({
        "success": True,
        "date": format_date(dispatch["date"]),
        "day_name": dispatch["day_name"],
        "is_weekday": dispatch["is_weekday"],
        "is_holiday": dispatch["is_holiday"],
        "total_subscribed": dispatch["total_subscribed"],
        "active_count": dispatch["active_count"],
        "paused_count": dispatch["paused_count"],
        "active_deliveries": dispatch["active_deliveries"],
        "paused_deliveries": dispatch["paused_deliveries"],
    }), 200


@app.route("/api/bills", methods=["GET"])
def api_bills():
    month_str = request.args.get("month")
    if not month_str:
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"

    year, month = map(int, month_str.split("-"))
    all_bills = service.generate_all_bills(year, month)
    grand_total = sum(b.total_amount for b in all_bills)

    sort_by = request.args.get("sort_by", "customer_name")
    order = request.args.get("order", "asc")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10))

    paginated, total_count, total_pages = service.paginate_bills(
        all_bills, sort_by=sort_by, order=order, page=page, per_page=per_page
    )

    return jsonify({
        "success": True,
        "month": month_str,
        "year": year,
        "grand_total": grand_total,
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "bills": [
            {
                "customer_name": b.customer_name,
                "customer_phone": b.customer_phone,
                "plan_name": b.plan_name,
                "total_month_weekdays": b.total_month_weekdays,
                "delivered_weekdays": b.delivered_weekdays,
                "paused_weekdays": b.paused_weekdays,
                "daily_rate": b.daily_rate,
                "total_amount": b.total_amount,
            }
            for b in paginated
        ],
    }), 200


@app.route("/api/bills/<phone>", methods=["GET"])
def api_single_bill(phone):
    month_str = request.args.get("month")
    if not month_str:
        today = date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"
    year, month = map(int, month_str.split("-"))

    try:
        bill = service.generate_bill(phone, year, month)
        return jsonify({
            "success": True,
            "bill": {
                "customer_name": bill.customer_name,
                "customer_phone": bill.customer_phone,
                "plan_name": bill.plan_name,
                "plan_monthly_price": bill.plan_monthly_price,
                "billing_month": f"{year:04d}-{month:02d}",
                "month_name": bill.month_name,
                "total_month_weekdays": bill.total_month_weekdays,
                "subscribed_weekdays": bill.subscribed_weekdays,
                "paused_weekdays": bill.paused_weekdays,
                "holiday_weekdays": bill.holiday_weekdays,
                "delivered_weekdays": bill.delivered_weekdays,
                "daily_rate": bill.daily_rate,
                "total_amount": bill.total_amount,
                "days_breakdown": [
                    {
                        "date": format_date(d.date),
                        "day_name": d.day_name,
                        "status": d.status.value,
                        "billable": d.billable,
                        "note": d.note,
                    }
                    for d in bill.days_breakdown
                ],
            },
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Interactive AI Assistant Endpoint.
    Provides step-by-step mathematical reasoning grounded strictly
    in verified company schemes and live database records with zero hallucination.
    """
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    phone = data.get("phone", "").strip() or None

    if not message:
        return jsonify({"success": False, "error": "Message parameter is required."}), 400

    try:
        result = chatbot.answer_query(message, phone=phone)
        return jsonify({
            "success": True,
            "reply": result["reply"],
            "reasoning": result["reasoning"],
            "intent": result["intent"],
            "grounded_facts": result["grounded_facts"],
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# ROUND 2 TWIST ENDPOINTS: LEVEL 1 (T1), LEVEL 2 (T6), LEVEL 3 (T4)
# =============================================================================

# --- Level 1 — T1 (integrate): /clock & /outbox ---
@app.route("/clock", methods=["POST"])
def api_clock():
    """
    Level 1 (T1): Dispatches morning notifications for customers due a delivery
    today (active subscription, weekday, not on holiday, not paused).
    Graded via /outbox.
    """
    data = request.get_json(silent=True) or {}
    target_date = data.get("date") or request.args.get("date")

    try:
        notifications = service.tick_clock(target_date)
        t_date = parse_date(target_date) if target_date else date.today()
        return jsonify({
            "success": True,
            "date": format_date(t_date),
            "dispatched_count": len(notifications),
            "outbox": notifications,
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/outbox", methods=["GET", "DELETE"])
def api_outbox():
    """
    Level 1 (T1): Notification Outbox.
    GET returns all queued/sent notifications.
    DELETE clears the outbox.
    """
    if request.method == "DELETE":
        service.clear_outbox()
        return jsonify({"success": True, "message": "Outbox cleared successfully"}), 200

    target_date = request.args.get("date")
    outbox_items = service.get_outbox(target_date)
    return jsonify({
        "success": True,
        "count": len(outbox_items),
        "outbox": outbox_items,
    }), 200


# --- Level 2 — T6 (lifecycle): Mid-Cycle Subscription Transfer ---
@app.route("/api/subscriptions/transfer", methods=["POST"])
def api_subscription_transfer():
    """
    Level 2 (T6): Transfer a subscription to a new customer mid-cycle.
    The plan and cycle carry over, billing splits strictly by who was served.
    """
    data = request.get_json() or {}
    from_phone = data.get("from_phone", "").strip()
    to_phone = data.get("to_phone", "").strip()
    to_name = data.get("to_name", "").strip()
    effective_date = data.get("effective_date", "").strip()
    to_address = data.get("to_address", "").strip()
    notes = data.get("notes", "").strip()

    if not from_phone or not to_phone or not effective_date:
        return jsonify({
            "success": False,
            "error": "from_phone, to_phone, and effective_date are required fields.",
        }), 400

    try:
        result = service.transfer_subscription(
            from_phone=from_phone,
            to_phone=to_phone,
            to_name=to_name,
            effective_date=effective_date,
            to_address=to_address,
            notes=notes,
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/subscriptions/transfers", methods=["GET"])
def api_list_transfers():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    transfers = service.list_transfers(year, month)
    return jsonify({"success": True, "transfers": transfers}), 200


# --- Level 3 — T4 (messy data): Ingest Messy Customer List ---
@app.route("/api/import", methods=["POST"])
@app.route("/api/customers/import", methods=["POST"])
def api_import_customers():
    """
    Level 3 (T4): Ingest a messy customer list into clean subscriptions.
    Accepts JSON array (or {'customers': [...]}) or CSV file upload.
    Returns { 'imported': [...], 'deduped': [...], 'rejected': [...] }.
    """
    records: list = []

    # Check for CSV file upload
    if "file" in request.files:
        uploaded_file = request.files["file"]
        if uploaded_file and uploaded_file.filename:
            content = uploaded_file.stream.read().decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                records.append({k.strip().lower(): v.strip() for k, v in row.items() if k})

    if not records:
        data = request.get_json(silent=True) or {}
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get("customers") or data.get("data") or []

    if not records:
        return jsonify({
            "success": False,
            "error": "No records found in payload. Provide a JSON array or multipart CSV file.",
        }), 400

    try:
        report = service.import_messy_customers(records)
        return jsonify(report), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Tiffin Platform on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
