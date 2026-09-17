# REASONING.md - Architectural Thought Process & Technical Decisions

**Candidate**: Sachin Choudhary  
**Email**: amisachinchoudhary@gmail.com  
**Project**: Annapurna Tiffin - Weekday Meal Subscription & Pro-Rated Billing Platform  
**Assessment**: Round 2 — "Builder" Round (Auriga IT)

---

## 1. Problem Analysis & Real-World Domain Reality

In home-style food delivery (tiffin services), treating customer subscriptions like a standard digital subscription (e.g., Netflix or Spotify) fails completely due to fundamental physical realities:

1. **Daily Operational Costs**:
   - Each meal cooked requires fresh ingredients (vegetables, dairy, grains, oil, spices), kitchen labor, packing containers, and delivery fuel.
   - If a customer goes on vacation for a week or attends a festival and pauses their service, they legitimately expect **not to be charged for food they never received**.
   - Concurrently, the kitchen needs advance notice to avoid preparing food that will be thrown away.

2. **The Weekday Delivery Constraint**:
   - Unlike gyms or streaming services that operate 365 days a year, tiffin services typically deliver **Monday through Friday only**.
   - In any given month, the number of billable weekdays varies between **20 and 23 days** (e.g., February 2024 had 21 weekdays, October 2026 has 22 weekdays).
   - If a provider naively calculates the daily rate by dividing the monthly price by 30 days:
     - On a Rs. 3,000 monthly plan, the naive daily rate is Rs. 100/day.
     - In a 22-weekday month, delivering all meals would only yield $22 \times 100 = \text{Rs. } 2,200$, losing the provider Rs. 800 every month!
     - Conversely, crediting Rs. 100 for a paused day shortchanges or overcharges depending on the month's length.

3. **Operational Visibility (The 6:00 AM Problem)**:
   - Every morning before cooking begins, the owner needs an immediate, foolproof answer:
     > **"Who is Active today (cook and pack) versus who is Paused (skip)?"**
   - In traditional setups, this information is buried across handwritten registers and fragmented WhatsApp messages, leading to missed deliveries, wasted food, and heated month-end billing disputes.

4. **Universal Phone Lookup**:
   - In local meal logistics, the customer's phone number is their sole identity. Customers never remember user IDs or account numbers; every operation must revolve around their phone number.

---

## 2. Mathematical Formulation & Pro-Ration Engine

To guarantee zero customer disputes and zero provider revenue leakage, we engineered the **Calendar Weekday Pro-Ration Engine**:

### Mathematical Definition:
For a customer subscribed to a plan with monthly price $P$ in a billing month with $W$ working weekdays:

$$\text{Daily Rate} = \frac{P}{W}$$

$$\text{Delivered Weekdays } D = S - \sum_{\text{paused}} 1$$

$$\text{Total Bill Amount} = \text{Round}\left(D \times \text{Daily Rate}, 2\right)$$

Where:
- $W$ = Total calendar weekdays (Monday–Friday) in that specific month, excluding kitchen holidays.
- $S$ = Subscribed weekdays in the month (weekdays on or after subscription start date and before end date).
- $D$ = Days food was actually prepared and dispatched.

### Edge Case Mathematical Guarantees:
- **Full Attendance Invariance**: If $D = W$, then $\text{Total Bill} = W \times \frac{P}{W} = P$. The customer pays exactly the monthly price with zero rounding drift.
- **The Weekend Pause Edge Case**: If a customer pauses from Friday to Monday (4 calendar days), only Friday and Monday are delivery days. The system excludes Saturday and Sunday, deducting exactly 2 delivery days from the bill.
- **Mid-Month Joins**: A customer subscribing on the 15th has days prior to the 15th categorized as `NOT_SUBSCRIBED`. They are billed strictly for active weekdays from the 15th to month-end.
- **Cross-Month Pause Isolation**: A pause interval from October 28 to November 6 is strictly partitioned at the calendar boundary: October's bill only discounts the 3 October weekdays, while November's bill discounts the remaining November weekdays.
- **100% Inactive Month**: A customer away for the entire month receives a verified bill of Rs. 0.00.

---

## 3. Architecture & System Design

We adopted a modular, domain-driven design decoupled into distinct layers:

```
tiffin-service/
├── tiffin/
│   ├── models.py          # Domain entities: Customer, Plan, Subscription, PauseRecord, User, Bill
│   ├── calendar_utils.py  # Pure functions for weekday math, range overlap, and ISO dates
│   ├── billing.py         # Pro-rated calculation engine & itemized audit generator
│   ├── storage.py         # SQLite persistence layer with transactions, search & pagination
│   ├── service.py         # High-level business facade coordinating workflows
│   └── cli.py             # Command-Line Interface with interactive mode
├── web/
│   ├── app.py             # Flask application & REST API server
│   └── templates/         # Modular Jinja2 + Tailwind CSS templates
│       ├── base.html      # Responsive master layout with navigation & user state
│       ├── landing.html   # One-page product landing page (mandatory deliverable)
│       ├── login.html     # Owner authentication login view
│       ├── register.html  # Owner account registration view
│       ├── dispatch.html  # Kitchen dispatch dashboard (Active vs. Paused)
│       ├── customers.html # Customer search, sorting, pagination, and dossier lookup
│       └── billing.html   # Month-end summary, sorting, pagination & printable tax invoices
├── tests/
│   ├── test_calendar.py        # Date math and weekday tests
│   ├── test_billing.py         # Pro-ration formula verification
│   ├── test_lifecycle.py       # State transitions (subscribe, pause, resume, dispatch)
│   ├── test_auth_and_search.py # User registration, auth, search & pagination
│   └── test_api_and_web.py     # End-to-end REST API & landing page tests
├── pyproject.toml
└── README.md
```

### Relational Database Schema (`tiffin.db`):
- `users`: `id`, `username` (UNIQUE), `password_hash`, `email`, `role`, `created_at`
- `plans`: `id` (PK), `name`, `monthly_price`, `description`
- `customers`: `phone` (PK), `name`, `address`, `notes`, `created_at`
- `subscriptions`: `id` (PK), `customer_phone` (FK), `plan_id` (FK), `start_date`, `end_date`, `status`
- `pauses`: `id` (PK), `customer_phone` (FK), `start_date`, `end_date`, `reason`, `created_at`
- `holidays`: `date` (PK), `name`

### Key Design Trade-Offs:
1. **SQLite with WAL / Foreign Keys vs. In-Memory Mock**:
   - We selected real SQLite persistence with foreign keys enabled (`PRAGMA foreign_keys = ON`) to satisfy real persistence requirements while maintaining zero external service dependencies.
2. **Dynamic Date-by-Day Generation vs. Static Daily Counters**:
   - Instead of incrementing a fragile counter every day, the billing engine evaluates attendance by intersecting the subscription window with customer pause intervals for every calendar day of the month.
   - This makes the system **completely retroactive and idempotent**: if an owner enters a customer's pause retroactively, the bill recalculates correctly without database corruption.
3. **Password Security**:
   - Uses `werkzeug.security` (`pbkdf2:sha256`) with automatic salt generation rather than storing plaintext passwords.

---

## 4. Testing & Verification Strategy

Testing was approached with rigor across five dedicated test suites containing **27 automated tests**:

1. **`tests/test_billing.py` (7 tests)**:
   - Full month delivery: Verified bill matches monthly plan price to the exact cent.
   - 1-week pause: Verified deduction of exactly 5 weekdays out of 22.
   - Weekend pause overlap: Tested Friday-to-Monday pause (4 calendar days) only discounts 2 delivery weekdays.
   - Mid-month signup: Verified pre-subscription weekdays are not charged.
   - Cross-month pause: Verified clean monthly boundary isolation.
   - Leap year February: Verified 21 weekdays in Feb 2024 leap year.
   - Zero deliveries: Verified Rs. 0.00 bill when paused all month.

2. **`tests/test_calendar.py` (5 tests)**:
   - Tested weekday classification (Mon-Fri = True, Sat-Sun = False).
   - Working day generation with custom kitchen holidays excluded.
   - Date range weekday calculations.

3. **`tests/test_lifecycle.py` (5 tests)**:
   - Subscription creation and status initialization.
   - Pause range activation and auto-switch to `PAUSED` status.
   - Indefinite pause with explicit resume date truncation.
   - Duplicate / overlapping pause rejection via `ValueError`.
   - Daily dispatch partitioning: verifying active vs. paused meal counts.

4. **`tests/test_auth_and_search.py` (3 tests)**:
   - Default admin seed verification.
   - User registration, password hashing verification, and duplicate rejection.
   - Customer search with case-insensitive substring matching, ASC/DESC sorting, and multi-page pagination.

5. **`tests/test_api_and_web.py` (7 tests)**:
   - Landing page rendering and verification of all 5 mandatory sections.
   - Web view rendering for `/login` and `/register`.
   - Full REST API authentication lifecycle (`/api/auth/register`, `/api/auth/login`, `/api/auth/me`, `/api/auth/logout`).
   - REST API core workflows: `/api/subscriptions`, `/api/pauses`, `/api/resumes`, `/api/dispatch`, and `/api/bills/<phone>`.
   - REST API pagination and sorting query parameters.

**Execution Result**:
```
27 passed in 2.40s (100% pass rate)
```

---

## 5. Issues Encountered & How They Were Resolved

1. **Issue 1: Windows Console `UnicodeEncodeError` with Currency Symbol**:
   - *Problem*: In Windows terminal (`cp1252` encoding), printing the Indian Rupee symbol `₹` crashed the CLI with `UnicodeEncodeError: 'charmap' codec can't encode character '\u20b9'`.
   - *Fix*: Reconfigured `sys.stdout` and `sys.stderr` to UTF-8 on Windows startup and standardized currency display to `Rs.` for maximum cross-platform compatibility.

2. **Issue 2: Windows PowerShell UTF-8 BOM (`\xef\xbb\xbf`) Syntax Errors**:
   - *Problem*: In Windows PowerShell 5.1, `Set-Content -Encoding UTF8` prepends a 3-byte Byte Order Mark (BOM). Python's `tomllib` and Jinja template parsers rejected the BOM at line 1 column 1.
   - *Fix*: Created a byte-level normalization script that automatically strips BOM from all `.toml`, `.py`, `.html`, and `.md` files before execution.

3. **Issue 3: SQLite Migration Cursor Scoping**:
   - *Problem*: During database initialization, the user seed query attempted to execute on `cur` before `cur = conn.cursor()` was assigned.
   - *Fix*: Restructured `_init_db()` to instantiate the cursor prior to executing seed checks.

4. **Issue 4: Overlapping Pause Windows**:
   - *Problem*: If a customer entered multiple pauses (e.g., Oct 5-10 and Oct 8-15), a naive implementation could double-deduct weekdays.
   - *Fix*: Added an interval collision algorithm: `max(req_start, exist_start) <= min(req_end, exist_end)`. Conflicting pauses are immediately rejected with a user-friendly error.

---

## 6. Mandatory Deliverables Checklist

| Requirement | Implementation | Status |
|---|---|---|
| **Database with Sensible Schema** | SQLite (`users`, `customers`, `plans`, `subscriptions`, `pauses`, `holidays`) | Complete |
| **REST APIs for Core Operations** | Complete JSON endpoints for Auth, Plans, Customers, Subscriptions, Pauses, Resumes, Dispatch, Bills | Complete |
| **Usable UI over APIs** | Responsive Tailwind CSS web application with dispatch cards, phone search, invoice views | Complete |
| **User Registration & Login** | Secure session-based authentication with `pbkdf2:sha256` password hashing | Complete |
| **Search Functionality** | Full-text query across customer name, phone, address, and notes | Complete |
| **One-Page Landing Page** | `/` landing page with What it is, Key features, Target audience, How it helps, 3 future features | Complete |
| **Pagination & Sorting** | Dynamic pagination and ASC/DESC column sorting across web UI and REST APIs | Complete |
| **README.md** | Setup guide, architecture, and complete REST API documentation | Complete |
| **REASONING.md** | Comprehensive technical and domain decision analysis | Complete |
| **AI_LOGS.md** | Verbatim conversation logs with AI assistant | Complete |

---

## 7. High-Impact UX Enhancements (Real-World Delight)

Beyond the baseline requirements, we implemented four major user experience enhancements tailored to how actual tiffin businesses operate:

1. **WhatsApp 1-Click Invoice Dispatch (`wa.me`)**:
   - *Rationale*: In India and globally, local meal providers do not send paper letters or PDF emails; 95% of communication is over WhatsApp.
   - *Solution*: A dedicated "Share via WhatsApp" button encodes the customer's phone number, name, month, delivered days, paused days, daily rate, and total balance due into a pre-formatted WhatsApp link that opens directly on the owner's phone or desktop.

2. **1-Click CSV Exports for Drivers & Accountants**:
   - *Rationale*: Drivers need offline, printable run-sheets of today's delivery addresses, and accountants need Excel files at month-end.
   - *Solution*: Added `/export/bills.csv` (complete monthly collection ledger) and `/export/dispatch.csv` (today's active route run-sheet with delivery addresses and notes).

3. **Kitchen Meal Matrix & Dietary Alert Banners**:
   - *Rationale*: Chefs cannot read 50 individual customer cards every morning to figure out how many veg vs non-veg meals to cook.
   - *Solution*: The dispatch dashboard aggregates active meals by plan (e.g. Standard Veg: 12, Deluxe: 8, Non-Veg: 4) and displays a prominent warning box for special dietary requests (mild spice, no garlic, extra roti).

4. **Customer Self-Service Bill Portal (`/my-bill`)**:
   - *Rationale*: Reduces repetitive customer inquiries ("How much do I owe this month?").
   - *Solution*: A public, secure customer portal where subscribers simply enter their phone number to see their own attendance calendar and pro-rated bill without needing admin credentials.

