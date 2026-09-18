"""
SQLite database storage layer for tiffin delivery service.
"""

from __future__ import annotations
from datetime import date, datetime
import sqlite3
from typing import List, Optional, Set

from .calendar_utils import format_date, parse_date
from .models import Customer, Kitchen, PauseRecord, Plan, Subscription, SubscriptionStatus, User
from werkzeug.security import generate_password_hash, check_password_hash


class Storage:
    def __init__(self, db_path: str = "tiffin.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kitchens (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    cuisine TEXT NOT NULL,
                    location TEXT NOT NULL,
                    rating REAL DEFAULT 4.8,
                    fssai_license TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    specialty TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    monthly_price REAL NOT NULL,
                    description TEXT DEFAULT '',
                    kitchen_id TEXT DEFAULT 'annapurna',
                    kitchen_name TEXT DEFAULT 'Annapurna Homestyle Kitchen'
                );

                CREATE TABLE IF NOT EXISTS customers (
                    phone TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    address TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_phone TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    FOREIGN KEY (customer_phone) REFERENCES customers(phone),
                    FOREIGN KEY (plan_id) REFERENCES plans(id)
                );

                CREATE TABLE IF NOT EXISTS pauses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_phone TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    reason TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (customer_phone) REFERENCES customers(phone)
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT DEFAULT '',
                    role TEXT DEFAULT 'owner',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS holidays (
                    date TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    delivery_date TEXT NOT NULL,
                    plan_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT DEFAULT 'SENT',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_phone TEXT NOT NULL,
                    to_phone TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    cycle_year INTEGER NOT NULL,
                    cycle_month INTEGER NOT NULL,
                    effective_date TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
            """)

            cur = conn.cursor()
            # Seed default admin user if none exists
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO users (username, password_hash, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("admin", generate_password_hash("admin123"), "admin@tiffin.local", "owner", datetime.now().isoformat())
                )
                conn.commit()

            # Ensure columns exist in plans table if migrated from earlier schema
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(plans)")
            cols = [c[1] for c in cur.fetchall()]
            if "kitchen_id" not in cols:
                conn.execute("ALTER TABLE plans ADD COLUMN kitchen_id TEXT DEFAULT 'annapurna'")
            if "kitchen_name" not in cols:
                conn.execute("ALTER TABLE plans ADD COLUMN kitchen_name TEXT DEFAULT 'Annapurna Homestyle Kitchen'")
            conn.commit()

            # Seed partner kitchens if none exist
            cur.execute("SELECT COUNT(*) FROM kitchens")
            if cur.fetchone()[0] == 0:
                SEED_KITCHENS = [
                    ("annapurna", "Annapurna Homestyle Kitchen", "Rajasthani & North Indian Pure Veg", "Malviya Nagar, Jaipur, Rajasthan", 4.9, "FSSAI-12223026000145", "+91 98290 12345", "Authentic Jaipur home-cooked tiffins prepared with cold-pressed mustard oil, desi ghee rotis, and seasonal organic vegetables.", "Dal Baati Churma (Fridays), Gatte ki Sabzi & Phulkas"),
                    ("shree_krishna", "Shree Krishna Gujarati & Jain Rasoi", "Pure Satvik Jain & Gujarati Thali", "Vaishali Nagar, Jaipur, Rajasthan", 4.8, "FSSAI-12224026000889", "+91 98292 67890", "Strictly pure Satvik preparations cooked without onion, garlic, or root vegetables. Light on spices, prepared daily in brass and steel cookware.", "Sev Tameta, Gujarati Kadhi, Phulka & Mohanthal"),
                    ("dabbawala_express", "Dabbawala Express Corporate Kitchen", "High-Protein & Low-Oil Balanced Meals", "DLF Cyber City, Gurugram / Delhi NCR", 4.7, "FSSAI-10822005000312", "+91 98110 54321", "Specially crafted for tech & corporate professionals. Calorie-counted, low GI carbs, macro-balanced, and leak-proof thermal sealed containers.", "Brown Rice Soya Bowls, Paneer Tikka Wraps, Multigrain Roti Packs"),
                    ("spice_route", "Spice Route South Indian Mess", "Authentic Kerala & Tamil Homestyle Meals", "Koramangala, Bengaluru, Karnataka", 4.9, "FSSAI-11223334000456", "+91 98450 78912", "Traditional South Indian meals served with aromatic Matta/Ponni rice, wood-pressed coconut oil, fresh rasam, sambar, and homemade vegetable poriyals.", "Avial, Malabar Parotta Meals, Chettinad Pepper Curry"),
                    ("punjab_dhaba", "Punjab Da Dhaba Tiffin House", "Hearty North Indian & Punjabi Homestyle", "Sector 18, Noida, Uttar Pradesh", 4.8, "FSSAI-12723055000781", "+91 98100 23456", "Rich, comforting home-style Punjabi food. Slow-simmered Maa ki Dal, soft Tandoori rotis, fragrant basmati rice, and fresh butter.", "Dal Makhani, Sarson Da Saag & Makki Roti (seasonal), Butter Chicken"),
                ]
                conn.executemany(
                    "INSERT INTO kitchens (id, name, cuisine, location, rating, fssai_license, phone, description, specialty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    SEED_KITCHENS,
                )
                conn.commit()

            # Seed or upsert default plans
            SEED_PLANS = [
                ("standard_veg", "Standard Vegetarian", 3000.0, "Nutritious home-style veg thali (4 Phulkas, Dal Tadka, Seasonal Sabzi, Rice, Salad) every weekday", "annapurna", "Annapurna Homestyle Kitchen"),
                ("special_veg", "Deluxe Vegetarian", 3800.0, "Deluxe thali with dessert, fresh curd, Shahi Paneer / Gatte, 4 ghee rotis & jeera rice", "annapurna", "Annapurna Homestyle Kitchen"),
                ("non_veg", "Non-Vegetarian", 4200.0, "Tender chicken/egg curry 3 days a week, Rajasthani veg thali on other weekdays", "annapurna", "Annapurna Homestyle Kitchen"),
                ("gujarati_satvik", "Gujarati Satvik Lunch Box", 3200.0, "Authentic sweet-tangy Dal, dry Shaak, 5 soft Rotlis, steamed rice, and homemade Chaas (No onion/garlic)", "shree_krishna", "Shree Krishna Gujarati & Jain Rasoi"),
                ("kathiyawadi_deluxe", "Kathiyawadi Royal Thali", 3600.0, "Spicy Sev Tameta / Ringan Bharta, 2 Bajra Rotla with white butter, Khichdi Kadhi & sweet", "shree_krishna", "Shree Krishna Gujarati & Jain Rasoi"),
                ("corporate_lite", "Corporate Calorie-Smart Box", 2800.0, "Portion-controlled 550 kcal balanced lunch: 3 multigrain rotis, dal, sautéed veg, sprouts salad", "dabbawala_express", "Dabbawala Express Corporate Kitchen"),
                ("cyberhub_combo", "High-Protein Executive Meal", 3500.0, "High-protein pack (32g protein): Tofu/Paneer bhurji, quinoa/brown rice, dal makhani, and Greek curd", "dabbawala_express", "Dabbawala Express Corporate Kitchen"),
                ("south_veg_meals", "Dakshin Traditional Veg Meals", 2900.0, "Steamed Ponni/Matta rice, Drumstick Sambar, Tomato Pepper Rasam, 2 Poriyals, Appalam & Moru", "spice_route", "Spice Route South Indian Mess"),
                ("chettinad_special", "Chettinad Non-Veg Feast", 4500.0, "Spicy Chettinad Chicken / Fish curry twice weekly, egg roast, and traditional South Indian sides", "spice_route", "Spice Route South Indian Mess"),
                ("punjabi_paneer_thali", "Shahi Punjabi Veg Thali", 3700.0, "Slow-cooked Dal Makhani, Paneer Butter Masala, 4 butter rotis, Jeera Pulao, Boondi Raita", "punjab_dhaba", "Punjab Da Dhaba Tiffin House"),
                ("dhaba_chicken_curry", "Pind Da Non-Veg Lunch", 4800.0, "Dhaba-style slow cooked Chicken Curry (Mon/Wed/Fri), Paneer Bhurji on other days, butter phulkas & salad", "punjab_dhaba", "Punjab Da Dhaba Tiffin House"),
            ]
            for pid, pname, price, pdesc, kid, kname in SEED_PLANS:
                conn.execute(
                    """
                    INSERT INTO plans (id, name, monthly_price, description, kitchen_id, kitchen_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        kitchen_id=coalesce(excluded.kitchen_id, plans.kitchen_id),
                        kitchen_name=coalesce(excluded.kitchen_name, plans.kitchen_name)
                    """,
                    (pid, pname, price, pdesc, kid, kname),
                )
            conn.commit()

            # Seed sample subscribers only for main application database, never for test databases
            if "test" not in self.db_path and self.db_path.endswith("tiffin.db"):
                cur.execute("SELECT COUNT(*) FROM customers")
                if cur.fetchone()[0] == 0:
                    now_str = datetime.now().isoformat()
                    today_start = date.today().replace(day=1).isoformat()
                    SAMPLE_CUSTOMERS = [
                        ("9876543210", "Ramesh Kumar", "Flat 402, Sunshine Heights, Malviya Nagar, Jaipur", "Medium spice, extra salad", "standard_veg"),
                        ("9829011223", "Priya Sharma", "B-12, Vaishali Nagar, Jaipur", "Strictly Jain - No onion garlic", "gujarati_satvik"),
                        ("9811099887", "Vikram Singhania", "Tower C, DLF Cyber City, Gurugram", "Deliver by 12:45 PM sharp", "cyberhub_combo"),
                        ("9845033445", "Ananya Rao", "14th Cross, 4th Block, Koramangala, Bengaluru", "Extra spicy rasam", "south_veg_meals"),
                        ("9810077665", "Harpreet Singh", "A-55, Sector 18, Noida", "Warm rotis, green chilli", "punjabi_paneer_thali"),
                    ]
                    for phone, name, addr, notes, plan_id in SAMPLE_CUSTOMERS:
                        conn.execute(
                            "INSERT INTO customers (phone, name, address, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                            (phone, name, addr, notes, now_str)
                        )
                        conn.execute(
                            "INSERT INTO subscriptions (customer_phone, plan_id, start_date, status) VALUES (?, ?, ?, 'ACTIVE')",
                            (phone, plan_id, today_start)
                        )
                    conn.commit()

    # --- Customer Methods ---
    def save_customer(self, customer: Customer) -> None:
        created_at = customer.created_at or datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO customers (phone, name, address, notes, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(phone) DO UPDATE SET
                    name=excluded.name,
                    address=excluded.address,
                    notes=excluded.notes
                """,
                (customer.phone, customer.name, customer.address, customer.notes, created_at),
            )
            conn.commit()

    def get_customer(self, phone: str) -> Optional[Customer]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM customers WHERE phone = ?", (phone,)).fetchone()
            if not row:
                return None
            return Customer(
                phone=row["phone"],
                name=row["name"],
                address=row["address"],
                notes=row["notes"],
                created_at=row["created_at"],
            )

    def list_customers(self) -> List[Customer]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY name ASC").fetchall()
            return [
                Customer(
                    phone=row["phone"],
                    name=row["name"],
                    address=row["address"],
                    notes=row["notes"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    # --- Plan Methods ---
    def save_plan(self, plan: Plan) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO plans (id, name, monthly_price, description, kitchen_id, kitchen_name)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    monthly_price=excluded.monthly_price,
                    description=excluded.description,
                    kitchen_id=excluded.kitchen_id,
                    kitchen_name=excluded.kitchen_name
                """,
                (plan.id, plan.name, plan.monthly_price, plan.description, plan.kitchen_id, plan.kitchen_name),
            )
            conn.commit()

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            if not row:
                return None
            k_id = row["kitchen_id"] if "kitchen_id" in row.keys() else "annapurna"
            k_name = row["kitchen_name"] if "kitchen_name" in row.keys() else "Annapurna Homestyle Kitchen"
            return Plan(
                id=row["id"],
                name=row["name"],
                monthly_price=row["monthly_price"],
                description=row["description"],
                kitchen_id=k_id,
                kitchen_name=k_name,
            )

    def list_plans(self) -> List[Plan]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM plans ORDER BY monthly_price ASC").fetchall()
            return [
                Plan(
                    id=row["id"],
                    name=row["name"],
                    monthly_price=row["monthly_price"],
                    description=row["description"],
                    kitchen_id=row["kitchen_id"] if "kitchen_id" in row.keys() else "annapurna",
                    kitchen_name=row["kitchen_name"] if "kitchen_name" in row.keys() else "Annapurna Homestyle Kitchen",
                )
                for row in rows
            ]

    # --- Kitchen Methods ---
    def save_kitchen(self, kitchen: Kitchen) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO kitchens (id, name, cuisine, location, rating, fssai_license, phone, description, specialty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    cuisine=excluded.cuisine,
                    location=excluded.location,
                    rating=excluded.rating,
                    fssai_license=excluded.fssai_license,
                    phone=excluded.phone,
                    description=excluded.description,
                    specialty=excluded.specialty
                """,
                (kitchen.id, kitchen.name, kitchen.cuisine, kitchen.location, kitchen.rating,
                 kitchen.fssai_license, kitchen.phone, kitchen.description, kitchen.specialty),
            )
            conn.commit()

    def get_kitchen(self, kitchen_id: str) -> Optional[Kitchen]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM kitchens WHERE id = ?", (kitchen_id,)).fetchone()
            if not row:
                return None
            return Kitchen(
                id=row["id"],
                name=row["name"],
                cuisine=row["cuisine"],
                location=row["location"],
                rating=row["rating"],
                fssai_license=row["fssai_license"],
                phone=row["phone"],
                description=row["description"],
                specialty=row["specialty"],
            )

    def list_kitchens(self) -> List[Kitchen]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM kitchens ORDER BY rating DESC, name ASC").fetchall()
            return [
                Kitchen(
                    id=row["id"],
                    name=row["name"],
                    cuisine=row["cuisine"],
                    location=row["location"],
                    rating=row["rating"],
                    fssai_license=row["fssai_license"],
                    phone=row["phone"],
                    description=row["description"],
                    specialty=row["specialty"],
                )
                for row in rows
            ]

    def get_plans_by_kitchen(self, kitchen_id: str) -> List[Plan]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM plans WHERE kitchen_id = ? ORDER BY monthly_price ASC", (kitchen_id,)).fetchall()
            return [
                Plan(
                    id=row["id"],
                    name=row["name"],
                    monthly_price=row["monthly_price"],
                    description=row["description"],
                    kitchen_id=row["kitchen_id"] if "kitchen_id" in row.keys() else kitchen_id,
                    kitchen_name=row["kitchen_name"] if "kitchen_name" in row.keys() else "Kitchen",
                )
                for row in rows
            ]

    # --- Subscription Methods ---
    def save_subscription(self, sub: Subscription) -> int:
        with self._get_connection() as conn:
            if sub.id:
                conn.execute(
                    """
                    UPDATE subscriptions
                    SET plan_id = ?, start_date = ?, end_date = ?, status = ?
                    WHERE id = ?
                    """,
                    (
                        sub.plan_id,
                        format_date(sub.start_date),
                        format_date(sub.end_date) if sub.end_date else None,
                        sub.status.value,
                        sub.id,
                    ),
                )
                conn.commit()
                return sub.id
            else:
                cur = conn.execute(
                    """
                    INSERT INTO subscriptions (customer_phone, plan_id, start_date, end_date, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        sub.customer_phone,
                        sub.plan_id,
                        format_date(sub.start_date),
                        format_date(sub.end_date) if sub.end_date else None,
                        sub.status.value,
                    ),
                )
                conn.commit()
                return cur.lastrowid

    def get_subscription_for_customer(self, phone: str) -> Optional[Subscription]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM subscriptions
                WHERE customer_phone = ?
                ORDER BY id DESC LIMIT 1
                """,
                (phone,),
            ).fetchone()
            if not row:
                return None
            return Subscription(
                id=row["id"],
                customer_phone=row["customer_phone"],
                plan_id=row["plan_id"],
                start_date=parse_date(row["start_date"]),
                end_date=parse_date(row["end_date"]) if row["end_date"] else None,
                status=SubscriptionStatus(row["status"]),
            )

    # --- Pause Methods ---
    def save_pause(self, pause: PauseRecord) -> int:
        created_at = pause.created_at or datetime.now().isoformat()
        with self._get_connection() as conn:
            if pause.id:
                conn.execute(
                    """
                    UPDATE pauses
                    SET start_date = ?, end_date = ?, reason = ?
                    WHERE id = ?
                    """,
                    (
                        format_date(pause.start_date),
                        format_date(pause.end_date) if pause.end_date else None,
                        pause.reason,
                        pause.id,
                    ),
                )
                conn.commit()
                return pause.id
            else:
                cur = conn.execute(
                    """
                    INSERT INTO pauses (customer_phone, start_date, end_date, reason, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pause.customer_phone,
                        format_date(pause.start_date),
                        format_date(pause.end_date) if pause.end_date else None,
                        pause.reason,
                        created_at,
                    ),
                )
                conn.commit()
                return cur.lastrowid

    def get_pauses_for_customer(self, phone: str) -> List[PauseRecord]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM pauses
                WHERE customer_phone = ?
                ORDER BY start_date ASC
                """,
                (phone,),
            ).fetchall()
            return [
                PauseRecord(
                    id=row["id"],
                    customer_phone=row["customer_phone"],
                    start_date=parse_date(row["start_date"]),
                    end_date=parse_date(row["end_date"]) if row["end_date"] else None,
                    reason=row["reason"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def get_active_pause(self, phone: str, target_date: date) -> Optional[PauseRecord]:
        pauses = self.get_pauses_for_customer(phone)
        for p in pauses:
            if p.is_active_on(target_date):
                return p
        return None

    # --- Holiday Methods ---
    def add_holiday(self, holiday_date: date, name: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO holidays (date, name) VALUES (?, ?) ON CONFLICT(date) DO UPDATE SET name=excluded.name",
                (format_date(holiday_date), name),
            )
            conn.commit()

    def get_holidays_in_month(self, year: int, month: int) -> Set[date]:
        prefix = f"{year:04d}-{month:02d}%"
        with self._get_connection() as conn:
            rows = conn.execute("SELECT date FROM holidays WHERE date LIKE ?", (prefix,)).fetchall()
            return {parse_date(row["date"]) for row in rows}

    # --- User Authentication Methods ---
    def create_user(self, user: User) -> User:
        created_at = user.created_at or datetime.now().isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, email, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user.username, user.password_hash, user.email, user.role, created_at),
            )
            conn.commit()
            user.id = cur.lastrowid
            user.created_at = created_at
            return user

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
            if not row:
                return None
            return User(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                email=row["email"],
                role=row["role"],
                created_at=row["created_at"],
            )

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            return User(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                email=row["email"],
                role=row["role"],
                created_at=row["created_at"],
            )

    # --- Search, Pagination and Sorting on Customers ---
    def search_customers(
        self,
        query: str = "",
        sort_by: str = "name",
        order: str = "asc",
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[List[Customer], int, int]:
        """
        Search customers by name, phone, address or notes.
        Supports sorting and pagination.
        Returns (customers_list, total_count, total_pages).
        """
        allowed_cols = {"name": "name", "phone": "phone", "created_at": "created_at"}
        col = allowed_cols.get(sort_by.lower(), "name")
        direction = "DESC" if order.lower() == "desc" else "ASC"

        query_filter = f"%{query.strip()}%" if query else "%"
        offset = max(0, (page - 1) * per_page)

        with self._get_connection() as conn:
            count_cur = conn.execute(
                """
                SELECT COUNT(*) FROM customers
                WHERE name LIKE ? OR phone LIKE ? OR address LIKE ? OR notes LIKE ?
                """,
                (query_filter, query_filter, query_filter, query_filter),
            )
            total_count = count_cur.fetchone()[0]
            total_pages = max(1, (total_count + per_page - 1) // per_page)

            query_sql = f"""
                SELECT * FROM customers
                WHERE name LIKE ? OR phone LIKE ? OR address LIKE ? OR notes LIKE ?
                ORDER BY {col} {direction}
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(
                query_sql,
                (query_filter, query_filter, query_filter, query_filter, per_page, offset),
            ).fetchall()

            customers = [
                Customer(
                    phone=r["phone"],
                    name=r["name"],
                    address=r["address"],
                    notes=r["notes"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
            return customers, total_count, total_pages

    # --- Level 1 (T1): Notification Outbox ---
    def save_outbox_entry(
        self,
        recipient: str,
        customer_name: str,
        delivery_date: str,
        plan_name: str,
        message: str,
        status: str = "SENT",
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO outbox (recipient, customer_name, delivery_date, plan_name, message, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (recipient, customer_name, delivery_date, plan_name, message, status, datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid

    def get_outbox(self, delivery_date: Optional[str] = None) -> List[dict]:
        with self._get_connection() as conn:
            if delivery_date:
                rows = conn.execute(
                    "SELECT * FROM outbox WHERE delivery_date = ? ORDER BY id ASC",
                    (delivery_date,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM outbox ORDER BY id ASC").fetchall()

            return [
                {
                    "id": r["id"],
                    "recipient": r["recipient"],
                    "customer_name": r["customer_name"],
                    "delivery_date": r["delivery_date"],
                    "plan_name": r["plan_name"],
                    "message": r["message"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def clear_outbox(self) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM outbox")
            conn.commit()

    # --- Level 2 (T6): Mid-Cycle Subscription Transfers ---
    def record_transfer(
        self,
        from_phone: str,
        to_phone: str,
        plan_id: str,
        cycle_year: int,
        cycle_month: int,
        effective_date: str,
        notes: str = "",
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO transfers (from_phone, to_phone, plan_id, cycle_year, cycle_month, effective_date, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (from_phone, to_phone, plan_id, cycle_year, cycle_month, effective_date, notes, datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid

    def get_transfers(self, cycle_year: Optional[int] = None, cycle_month: Optional[int] = None) -> List[dict]:
        with self._get_connection() as conn:
            if cycle_year and cycle_month:
                rows = conn.execute(
                    "SELECT * FROM transfers WHERE cycle_year = ? AND cycle_month = ? ORDER BY id ASC",
                    (cycle_year, cycle_month),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM transfers ORDER BY id DESC").fetchall()

            return [
                {
                    "id": r["id"],
                    "from_phone": r["from_phone"],
                    "to_phone": r["to_phone"],
                    "plan_id": r["plan_id"],
                    "cycle_year": r["cycle_year"],
                    "cycle_month": r["cycle_month"],
                    "effective_date": r["effective_date"],
                    "notes": r["notes"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def get_transfer_for_customer(self, phone: str, cycle_year: int, cycle_month: int) -> Optional[dict]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM transfers
                WHERE (from_phone = ? OR to_phone = ?) AND cycle_year = ? AND cycle_month = ?
                ORDER BY id DESC LIMIT 1
                """,
                (phone, phone, cycle_year, cycle_month),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "from_phone": row["from_phone"],
                "to_phone": row["to_phone"],
                "plan_id": row["plan_id"],
                "cycle_year": row["cycle_year"],
                "cycle_month": row["cycle_month"],
                "effective_date": row["effective_date"],
                "notes": row["notes"],
                "created_at": row["created_at"],
            }
