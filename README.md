# 🍱 Annapurna Tiffin - Management & Pro-Rated Billing Platform

A full-stack, home-style tiffin (lunch delivery) management and pro-rated billing operating system. Built for Round 2 ("Builder" Round) of the Auriga IT Campus Recruitment Drive.

Customers subscribe to a monthly meal plan for weekday lunch deliveries, pause dynamically for travel, illness, or festivals, and are **billed strictly for the meals actually delivered**.

---

## 🌟 Solution Highlights

- **Database Persistence**: SQLite schema with transactional foreign-key integrity (`users`, `customers`, `plans`, `subscriptions`, `pauses`, `holidays`).
- **REST APIs**: Full suite of JSON REST endpoints with status codes, error handling, and parameter validation.
- **Modern Responsive Web UI**: Tailwind CSS interface with kitchen dispatch sheet, phone lookup dossier, and 1-click printable tax invoices.
- **User Authentication**: Secure user registration, login, session cookies, and `pbkdf2:sha256` password hashing.
- **Search, Pagination & Sorting**: Case-insensitive search across customer names, phone numbers, and addresses with dynamic sorting (`asc`/`desc`) and multi-page pagination.
- **WhatsApp 1-Click Bill Sharing**: Instant pre-formatted WhatsApp billing notification generator (`wa.me`) with line-by-line breakdown for easy customer sharing.
- **1-Click CSV Exports**: One-click download of Monthly Billing Ledgers (`/export/bills.csv`) and Daily Delivery Run-Sheets (`/export/dispatch.csv`).
- **Interactive Zero-Hallucination AI Assistant (`/assistant`, `/api/chat`)**: Transparent conversational engine with step-by-step mathematical reasoning, strictly grounded in verified company meal schemes and database records without hallucination.
- **Customer Self-Service Bill Portal (`/my-bill`)**: Public portal where subscribers check their personal live attendance calendar and verified pro-rated bill by phone number.
- **Kitchen Meal Plan Matrix & Dietary Alerts**: Real-time kitchen tally of meal plans (Standard Veg, Deluxe Veg, Non-Veg) and special dietary instructions (no onion-garlic, extra roti, mild spice).
- **One-Page Product Landing Page**: Integrated showcase covering What it is, Key features, Target audience, How it helps, and Three features to build next.
- **Automated Test Suite**: 42 comprehensive unit, integration, twist, and API tests with 100% pass rate.

---

## 🚀 Quickstart & Setup Guide

### 1. Prerequisites
- Python 3.8+ (tested on Python 3.13)
- `pip` package manager

### 2. Clone Repository
```bash
git clone https://github.com/sachinchoudhary12321/tiffin-service.git
cd tiffin-service
```

### 3. Install Dependencies
```bash
pip install -e .
# Or install directly:
pip install flask pytest
```

### 4. Run the Web Application
```bash
python web/app.py
```
Open your browser at **[http://localhost:5000](http://localhost:5000)**.

> **Default Demo Login**:  
> **Username**: `admin`  
> **Password**: `admin123`  
> *(You can also click "Register" on the top-right to create a new owner account).*

---

## 🧪 Running Automated Tests & Debugging

Run the full pytest suite:
```bash
python -m pytest -v
```

### Running Specific Test Suites:
```bash
# Pro-ration billing math tests
pytest tests/test_billing.py -v

# Calendar and weekday calculations
pytest tests/test_calendar.py -v

# Subscription, pause, resume lifecycle tests
pytest tests/test_lifecycle.py -v

# User authentication, customer search & pagination
pytest tests/test_auth_and_search.py -v

# REST API and Web view tests
pytest tests/test_api_and_web.py -v

# Zero-hallucination AI reasoning chatbot tests
pytest tests/test_chatbot.py -v

# Official Round 2 Twists (Level 1 T1 clock/outbox, Level 2 T6 transfer, Level 3 T4 import)
pytest tests/test_twists_t1_t6_t4.py -v
```

### Debugging Tips:
- **Database Inspection**: The SQLite database is stored at `tiffin.db` in the project root. You can inspect it with `sqlite3 tiffin.db` or GUI tools like DB Browser for SQLite.
- **Custom Port**: Run `PORT=8000 python web/app.py` to bind to an alternate port.
- **Clean Database Reset**: Delete `tiffin.db` and restart the application; the schema and default meal plans/admin user will auto-seed automatically.

---

## 📡 REST API Endpoints Specification

All API endpoints return JSON. Successful responses return `"success": true`.

### Authentication Endpoints

#### `POST /api/auth/register`
Register a new kitchen owner account.
- **Request Body**:
  ```json
  {
    "username": "jaipur_kitchen",
    "password": "securepassword",
    "email": "owner@jaipur.com"
  }
  ```
- **Response (201 Created)**:
  ```json
  {
    "success": true,
    "message": "User registered successfully",
    "user": {
      "id": 2,
      "username": "jaipur_kitchen",
      "email": "owner@jaipur.com",
      "role": "owner"
    }
  }
  ```

#### `POST /api/auth/login`
Authenticate and initiate session.
- **Request Body**:
  ```json
  {
    "username": "admin",
    "password": "admin123"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Login successful",
    "user": { "id": 1, "username": "admin", "role": "owner" }
  }
  ```

#### `POST /api/auth/logout`
Terminates active user session.
- **Response (200 OK)**: `{"success": true, "message": "Logged out successfully"}`

#### `GET /api/auth/me`
Retrieve active logged-in user profile.
- **Response (200 OK / 401 Unauthorized)**:
  ```json
  {
    "success": true,
    "authenticated": true,
    "user": { "id": 1, "username": "admin", "email": "admin@tiffin.local", "role": "owner" }
  }
  ```

---

### Meal Plans Endpoint

#### `GET /api/plans`
Retrieve all available meal subscription plans.
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "plans": [
      {
        "id": "standard_veg",
        "name": "Standard Vegetarian",
        "monthly_price": 3000.0,
        "description": "Nutritious home-style veg thali every weekday"
      },
      {
        "id": "special_veg",
        "name": "Deluxe Vegetarian",
        "monthly_price": 3800.0,
        "description": "Includes dessert, curd & specialty paneer dishes"
      },
      {
        "id": "non_veg",
        "name": "Non-Vegetarian",
        "monthly_price": 4200.0,
        "description": "Chicken/egg dishes 3 days a week, veg on other weekdays"
      }
    ]
  }
  ```

---

### Customers & Subscriptions Endpoints

#### `GET /api/customers`
Retrieve paginated, searchable, and sorted customers list.
- **Query Parameters**:
  - `query` (optional): search term (matches name, phone, address, notes)
  - `sort_by` (optional): `name`, `phone`, `created_at` (default: `name`)
  - `order` (optional): `asc`, `desc` (default: `asc`)
  - `page` (optional): page number (default: `1`)
  - `per_page` (optional): items per page (default: `10`)
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "query": "Amit",
    "sort_by": "name",
    "order": "asc",
    "page": 1,
    "per_page": 10,
    "total_count": 1,
    "total_pages": 1,
    "customers": [
      {
        "phone": "9876543210",
        "name": "Amit Sharma",
        "address": "Flat 301, Marvel Apts",
        "notes": "Less spicy",
        "created_at": "2026-09-17T14:41:31"
      }
    ]
  }
  ```

#### `GET /api/customers/<phone>`
Look up customer dossier, active pause, live status, and current month bill estimate.
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "customer": {
      "name": "Amit Sharma",
      "phone": "9876543210",
      "address": "Flat 301, Marvel Apts"
    },
    "subscription": {
      "plan_id": "standard_veg",
      "start_date": "2026-10-01",
      "status": "ACTIVE"
    },
    "status_today": {
      "status": "PAUSED",
      "is_delivery_day": false,
      "pause_reason": "Visiting parents"
    },
    "current_month_estimate": {
      "month": "October",
      "delivered_weekdays": 17,
      "paused_weekdays": 5,
      "total_amount": 2318.18
    }
  }
  ```

#### `POST /api/subscriptions`
Subscribe a customer to a monthly weekday lunch plan.
- **Request Body**:
  ```json
  {
    "name": "Rohit Sen",
    "phone": "9899001122",
    "plan_id": "non_veg",
    "address": "Villa 14, Palm Meadows",
    "start_date": "2026-10-01",
    "notes": "No coriander"
  }
  ```
- **Response (201 Created)**:
  ```json
  {
    "success": true,
    "message": "Subscription created successfully",
    "subscription": {
      "phone": "9899001122",
      "plan_id": "non_veg",
      "start_date": "2026-10-01",
      "status": "ACTIVE"
    }
  }
  ```

---

### Pause & Resume Lifecycle Endpoints

#### `POST /api/pauses`
Pause lunch delivery for a customer (fixed date range or indefinite).
- **Request Body**:
  ```json
  {
    "phone": "9876543210",
    "from_date": "2026-10-05",
    "to_date": "2026-10-09",
    "reason": "Traveling to Jaipur"
  }
  ```
- **Response (201 Created)**:
  ```json
  {
    "success": true,
    "message": "Delivery paused successfully",
    "pause": {
      "id": 1,
      "phone": "9876543210",
      "from_date": "2026-10-05",
      "to_date": "2026-10-09",
      "reason": "Traveling to Jaipur"
    }
  }
  ```

#### `POST /api/resumes`
Resume delivery for a paused customer.
- **Request Body**:
  ```json
  {
    "phone": "9876543210",
    "resume_date": "2026-10-10"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "resumed": true
  }
  ```

---

### Kitchen Dispatch & Pro-Rated Billing Endpoints

#### `GET /api/dispatch`
Get the morning kitchen prep and dispatch counts for any target date.
- **Query Parameters**: `date=YYYY-MM-DD` (optional, default: today)
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "date": "2026-10-07",
    "day_name": "Wednesday",
    "is_weekday": true,
    "is_holiday": false,
    "total_subscribed": 3,
    "active_count": 2,
    "paused_count": 1,
    "active_deliveries": [
      {
        "name": "Priya Nair",
        "phone": "9811223344",
        "plan_name": "Deluxe Vegetarian",
        "address": "Tower B-502, Orchid Woods"
      },
      {
        "name": "Rohit Sen",
        "phone": "9899001122",
        "plan_name": "Non-Vegetarian",
        "address": "Villa 14, Palm Meadows"
      }
    ],
    "paused_deliveries": [
      {
        "name": "Amit Sharma",
        "phone": "9876543210",
        "plan_name": "Standard Vegetarian",
        "reason": "Traveling to Jaipur",
        "resume_date": "2026-10-09"
      }
    ]
  }
  ```

#### `GET /api/bills`
Generate paginated and sorted monthly billing summary for all subscribers.
- **Query Parameters**:
  - `month` (e.g. `2026-10`)
  - `sort_by` (`customer_name`, `total_amount`, `delivered_weekdays`, `phone`)
  - `order` (`asc`, `desc`)
  - `page` & `per_page`
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "month": "2026-10",
    "grand_total": 9800.0,
    "page": 1,
    "per_page": 10,
    "total_count": 3,
    "total_pages": 1,
    "bills": [
      {
        "customer_name": "Amit Sharma",
        "customer_phone": "9876543210",
        "plan_name": "Standard Vegetarian",
        "total_month_weekdays": 22,
        "delivered_weekdays": 17,
        "paused_weekdays": 5,
        "daily_rate": 136.3636,
        "total_amount": 2318.18
      }
    ]
  }
  ```

#### `GET /api/bills/<phone>`
Retrieve detailed pro-rated bill with itemized daily attendance audit.
- **Query Parameters**: `month=YYYY-MM` (e.g., `2026-10`)
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "bill": {
      "customer_name": "Amit Sharma",
      "customer_phone": "9876543210",
      "plan_name": "Standard Vegetarian",
      "plan_monthly_price": 3000.0,
      "billing_month": "2026-10",
      "month_name": "October",
      "total_month_weekdays": 22,
      "subscribed_weekdays": 22,
      "paused_weekdays": 5,
      "holiday_weekdays": 0,
      "delivered_weekdays": 17,
      "daily_rate": 136.3636,
      "total_amount": 2318.18,
      "days_breakdown": [
        {
          "date": "2026-10-01",
          "day_name": "Thursday",
          "status": "DELIVERED",
          "billable": true,
          "note": "Lunch delivered"
        },
        {
          "date": "2026-10-05",
          "day_name": "Monday",
          "status": "PAUSED",
          "billable": false,
          "note": "Paused: Traveling to Jaipur"
        }
      ]
    }
  }
  ```

---

### AI Reasoning Assistant Endpoint

#### `POST /api/chat`
Ask the interactive conversational assistant questions about meal schemes, pro-rated billing logic, pause policies, hypothetical scenario simulations, or live customer phone account lookups. Grounded strictly in company rules with zero hallucination and transparent step-by-step reasoning.
- **Request Body**:
  ```json
  {
    "message": "If I pause for 5 days on standard veg, how much will I pay?",
    "phone": "9876543210"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "intent": "simulation",
    "reply": "🧮 Step-by-Step Scenario Simulation:\n\nIf you subscribe to the Standard Vegetarian (Rs. 3000.00/month) and pause for 5 weekdays:\n\n1. Total Weekdays in Month: 22 days\n2. Daily Rate: Rs. 3000.00 / 22 = Rs. 136.36/meal\n3. Lunches Delivered: 22 - 5 = 17 days\n4. Absence Credit: 5 x 136.36 = Rs. 681.82\n\n💰 Your Pro-Rated Bill Would Be: Rs. 2318.18\n(You only pay for the 17 meals actually delivered to you).",
    "reasoning": [
      "Simulating scenario: 5 paused weekdays on Standard Vegetarian.",
      "Baseline: Standard month with 22 working weekdays.",
      "Formula: (17 delivered days / 22 total weekdays) * Rs. 3000.0.",
      "Resulting calculated bill: Rs. 2318.18."
    ],
    "grounded_facts": [
      "Simulated plan: Standard Vegetarian",
      "Paused days: 5",
      "Delivered days: 17",
      "Simulated bill: Rs. 2318.18"
    ]
  }
  ```

---

### 🎯 Official Graded Twists Endpoints (Levels 1, 2, 3)

#### Level 1 — T1 (integrate): Morning Clock & Notification Outbox

##### `POST /clock`
Simulate the morning delivery trigger for a target date. Identifies all customers due a delivery today (**active, weekday, not paused, not kitchen holiday**) and pushes them to the Notification Service Outbox.
- **Request Body**:
  ```json
  {
    "date": "2026-10-01"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "date": "2026-10-01",
    "is_weekday": true,
    "is_holiday": false,
    "dispatched_count": 14,
    "message": "Processed 14 notifications into outbox"
  }
  ```

##### `GET /outbox`
Inspect notifications queued by the clock runner.
- **Query Parameters**: `date=YYYY-MM-DD` (optional, default: all pending)
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "count": 1,
    "outbox": [
      {
        "id": 1,
        "target_date": "2026-10-01",
        "customer_phone": "9876543210",
        "customer_name": "Amit Sharma",
        "plan_id": "standard_veg",
        "plan_name": "Standard Vegetarian",
        "message": "Good morning Amit Sharma! Your Standard Vegetarian lunch delivery is scheduled for today (2026-10-01). Enjoy your meal!",
        "status": "QUEUED"
      }
    ]
  }
  ```

##### `DELETE /outbox`
Clear processed or test notifications from the outbox.

---

#### Level 2 — T6 (lifecycle): Mid-Cycle Subscription Transfer

##### `POST /api/subscriptions/transfer`
Transfer an active subscription to a new customer mid-cycle. The plan and billing cycle carry over seamlessly, and billing splits strictly by who was actually served.
- **Request Body**:
  ```json
  {
    "from_phone": "9811111111",
    "to_phone": "9822222222",
    "to_name": "Neha Gupta",
    "effective_date": "2026-10-15",
    "to_address": "Flat 402, Green Meadows",
    "notes": "Transfer mid-month"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "transfer_id": 1,
    "from_phone": "9811111111",
    "to_phone": "9822222222",
    "to_name": "Neha Gupta",
    "plan_id": "standard_veg",
    "plan_name": "Standard Vegetarian",
    "effective_date": "2026-10-15",
    "cycle": "2026-10",
    "message": "Subscription for Standard Vegetarian transferred from 9811111111 to Neha Gupta (9822222222) effective 2026-10-15. Billing splits by who was served."
  }
  ```

##### `GET /api/subscriptions/transfers`
Audit log of all mid-cycle transfers.
- **Query Parameters**: `year=YYYY` & `month=MM` (optional)

---

#### Level 3 — T4 (messy data): Ingest Messy Customer List

##### `POST /api/import` or `POST /api/customers/import`
Ingest messy customer spreadsheets containing duplicated phone numbers, inconsistent phone formats (`+91`, spaces, dashes), mixed date formats (`DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD`, text months), and blanks into clean subscriptions with an `{ imported, deduped, rejected }` report.
- **Payload**: Accepts either a **multipart CSV file upload** (`file`) or a **JSON array** (`customers`).
- **Sample Request (JSON)**:
  ```json
  {
    "customers": [
      { "name": "Rahul Sharma", "phone": "+91 98666 66666", "start_date": "01/10/2026", "plan_id": "standard_veg" },
      { "name": "Pooja Verma", "phone": "98777-77777", "start_date": "2026-10-01" },
      { "name": "Deepak (Duplicate)", "phone": "9877777777", "start_date": "2026-10-15" },
      { "name": "", "phone": "9888888888" }
    ]
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "success": true,
    "imported": [
      { "row": 1, "name": "Rahul Sharma", "phone": "+919866666666", "plan_id": "standard_veg", "start_date": "2026-10-01" },
      { "row": 2, "name": "Pooja Verma", "phone": "9877777777", "plan_id": "standard_veg", "start_date": "2026-10-01" }
    ],
    "deduped": [
      { "row": 3, "phone": "9877777777", "name": "Deepak (Duplicate)", "reason": "Duplicate phone number encountered in current import batch (skipped duplicate)" }
    ],
    "rejected": [
      { "row": 4, "raw": { "name": "", "phone": "9888888888" }, "reason": "Missing customer name (blank field)" }
    ],
    "summary": {
      "total_rows": 4,
      "imported_count": 2,
      "deduped_count": 1,
      "rejected_count": 1
    }
  }
  ```

---

## 🖥️ Command-Line Interface (CLI)

The package includes an owner CLI for command-line operations:

```bash
# View available plans
python -m tiffin.cli plans

# Subscribe customer
python -m tiffin.cli subscribe --name "Amit Sharma" --phone 9876543210 --plan standard_veg --address "Flat 301"

# Pause customer
python -m tiffin.cli pause --phone 9876543210 --from 2026-10-05 --to 2026-10-09 --reason "Visiting parents"

# Resume customer
python -m tiffin.cli resume --phone 9876543210 --date 2026-10-10

# Look up customer dossier
python -m tiffin.cli lookup 9876543210

# Daily kitchen dispatch
python -m tiffin.cli dispatch --date 2026-10-07

# Itemized month-end bill
python -m tiffin.cli bill --phone 9876543210 --month 2026-10 --itemized

# All customers billing ledger
python -m tiffin.cli bills --month 2026-10

# Interactive terminal menu
python -m tiffin.cli interactive
```

---

## 📜 Submission Deliverables

- `README.md` — Setup, run, debug, and complete REST API documentation.
- `REASONING.md` — In-depth architectural thought process, domain breakdown, testing, and debugging.
- `AI_LOGS.md` — Complete conversation with the AI tool, pasted as-is without alterations.
