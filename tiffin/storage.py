"""
SQLite database storage layer for tiffin delivery service.
"""

from __future__ import annotations
from datetime import date, datetime
import sqlite3
from typing import List, Optional, Set

from .calendar_utils import format_date, parse_date
from .models import Customer, PauseRecord, Plan, Subscription, SubscriptionStatus, User
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
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    monthly_price REAL NOT NULL,
                    description TEXT DEFAULT ''
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

            # Seed default plans if none exist
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM plans")
            if cur.fetchone()[0] == 0:
                conn.executemany(
                    "INSERT INTO plans (id, name, monthly_price, description) VALUES (?, ?, ?, ?)",
                    [
                        ("standard_veg", "Standard Vegetarian", 3000.0, "Nutritious home-style veg thali every weekday"),
                        ("special_veg", "Deluxe Vegetarian", 3800.0, "Includes dessert, curd & specialty paneer dishes"),
                        ("non_veg", "Non-Vegetarian", 4200.0, "Chicken/egg dishes 3 days a week, veg on other weekdays"),
                    ],
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
                INSERT INTO plans (id, name, monthly_price, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    monthly_price=excluded.monthly_price,
                    description=excluded.description
                """,
                (plan.id, plan.name, plan.monthly_price, plan.description),
            )
            conn.commit()

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            if not row:
                return None
            return Plan(
                id=row["id"],
                name=row["name"],
                monthly_price=row["monthly_price"],
                description=row["description"],
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
