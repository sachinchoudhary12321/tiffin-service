# 🍱 Tiffin Service Subscription & Pro-Rated Billing Engine

A home-style lunch delivery (tiffin) management system designed for independent meal providers. Customers subscribe to a monthly plan for weekday lunch deliveries, pause dynamically for travel or festivals, and are **billed only for the days food was actually delivered**.

Built with a domain-driven Python core, transactional SQLite storage, a rich CLI, a visual Web Dashboard, and a 100% passing automated test suite.

---

## 📖 The Storyline & Problem

In home-style food delivery, charging a flat monthly subscription fails whenever real life happens:
1. **Weekdays Only**: Deliveries occur Monday through Friday (typically 20 to 23 days per month, not 30).
2. **Fresh Food Prep Costs**: Every lunch prepared requires fresh ingredients, kitchen labor, and fuel. When customers travel or take time off, they expect not to be charged, and the kitchen needs to know not to cook for them.
3. **The Pro-Ration Trap**: A flat monthly rate divided naively by 30 days under-bills the customer on active days and miscalculates credits on pause days.
4. **Kitchen Operations**: Every morning at 6 AM, the owner must know: **Who is Active (cook & pack) vs. who is Paused?**
5. **Universal Lookup by Phone**: In local food delivery, the customer's phone number is their sole identity.

---

## 📐 Mathematical Pro-Ration Model

The system implements the **Calendar Weekday Pro-Ration Engine**:

$$\text{Daily Rate} = \frac{\text{Monthly Plan Price}}{\text{Total Weekdays in the Billing Month}}$$

$$\text{Total Bill} = \text{Round}\left(\text{Delivered Weekdays} \times \text{Daily Rate}, 2\right)$$

### Key Advantages:
- **Full Attendance Guarantee**: If a customer receives deliveries every weekday of that month, their bill is **exactly** the monthly plan price.
- **Fair Absence Credit**: If a customer is paused for 5 weekdays in a 22-weekday month (\$2,200 plan), they pay $\frac{17}{22} \times 2200 = \$1,700.00$.
- **Weekend Invariance**: Pausing from Friday to Monday (4 calendar days) only discounts 2 delivery weekdays (Friday & Monday), not Saturday or Sunday.
- **Mid-Month Join**: A customer subscribing on the 15th is only charged for weekdays following their start date.
- **Cross-Month Isolation**: Pausing across month boundaries (e.g., Oct 28 to Nov 5) deducts October days from October's bill and November days from November's bill.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.8+ (tested on Python 3.13)
- Git

### Installation
```bash
git clone https://github.com/sachinchoudhary12321/tiffin-service.git
cd tiffin-service
pip install -e .
```

---

## 🖥️ Command-Line Interface (CLI)

The package includes an owner CLI for rapid operations:

### 1. View Available Plans
```bash
python -m tiffin.cli plans
```

### 2. Subscribe a Customer
```bash
python -m tiffin.cli subscribe \
  --name "Amit Sharma" \
  --phone "9876543210" \
  --plan "standard_veg" \
  --address "Flat 301, Marvel Apts" \
  --start-date "2026-10-01"
```

### 3. Pause Deliveries
Schedule a pause with an exact return date or pause indefinitely:
```bash
# Fixed range (e.g. traveling for 1 week)
python -m tiffin.cli pause --phone 9876543210 --from 2026-10-05 --to 2026-10-09 --reason "Visiting parents"

# Indefinite pause
python -m tiffin.cli pause --phone 9876543210 --from 2026-10-15 --reason "Medical leave"
```

### 4. Resume Deliveries
```bash
python -m tiffin.cli resume --phone 9876543210 --date 2026-10-20
```

### 5. Kitchen Dispatch Sheet (Active vs. Paused)
Run this every morning to generate the prep and dispatch counts:
```bash
python -m tiffin.cli dispatch --date 2026-10-07
```

### 6. Phone Lookup
View customer profile, live status (Active vs. Paused), and month-to-date bill estimate:
```bash
python -m tiffin.cli lookup 9876543210
```

### 7. Generate Month-End Pro-Rated Bill
```bash
# Customer bill with line-by-line itemized calendar audit
python -m tiffin.cli bill --phone 9876543210 --month 2026-10 --itemized

# Summary of all customers for the month
python -m tiffin.cli bills --month 2026-10
```

### 8. Interactive Terminal Mode
```bash
python -m tiffin.cli interactive
```

---

## 🌐 Web Dashboard

A visual control panel for mobile or desktop browsers:

```bash
python web/app.py
```
Open **http://localhost:5000** in your browser:
- **Kitchen Dispatch**: Real-time counter of tiffins to cook today vs. skipped meals.
- **Customer Directory & Phone Search**: View pause history, subscribe new customers, and toggle pause/resume.
- **Billing & Invoice Generator**: 1-click printable tax invoice with day-by-day delivery breakdown for customers.

---

## 🧪 Automated Testing

Run the full test suite covering billing math, calendar logic, and state transitions:

```bash
pytest -v
```

### Test Coverage Highlights:
- `test_full_month_delivery_matches_plan_price`: Validates zero rounding drift on full attendance.
- `test_one_week_pause_pro_rating`: Validates pro-rated deduction for paused days.
- `test_weekend_overlapping_pause`: Ensures non-working weekend days are not counted as pause credits.
- `test_mid_month_subscription_pro_rating`: Ensures prior weekdays are excluded for mid-month subscribers.
- `test_cross_month_pause_isolation`: Confirms pause windows spanning two months are separated cleanly.
- `test_entire_month_paused_results_in_zero_bill`: Confirms $0.00 bill when away the whole month.
- `test_overlap_pause_rejected`: Rejects conflicting or duplicate pause date ranges.
- `test_leap_year_february_weekdays`: Tests 29-day February weekday edge cases.

---

## 📂 Project Structure

```
tiffin-service/
├── tiffin/
│   ├── __init__.py          # Package exports
│   ├── models.py            # Domain entities (Customer, Plan, Subscription, PauseRecord, Bill)
│   ├── calendar_utils.py    # Weekday counting, holidays, range calculations
│   ├── billing.py           # Pro-rated calculation engine & itemized day breakdown
│   ├── service.py           # High-level business facade (subscribe, pause, resume, dispatch)
│   ├── storage.py           # SQLite repository with transactional integrity
│   └── cli.py               # Command-line interface with interactive mode
├── web/
│   ├── app.py               # Flask application server
│   └── templates/
│       └── index.html       # Responsive Tailwind CSS dashboard and invoice view
├── tests/
│   ├── test_calendar.py     # Weekday and date utilities tests
│   ├── test_billing.py      # Mathematical pro-rating tests
│   └── test_lifecycle.py    # Lifecycle, dispatch, and phone lookup tests
├── pyproject.toml           # Package metadata and dependencies
└── README.md
```

---

## 📜 License
MIT License. Free for commercial and personal use.
