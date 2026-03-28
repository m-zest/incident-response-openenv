"""
Initialize the SQLite database with realistic SRE application data.

Creates tables for users, transactions, sessions, and api_logs
with seeded random data for reproducible simulations.
"""

import sqlite3
import random
import hashlib
import os
from datetime import datetime, timedelta

DB_PATH = os.environ.get("SRE_DB_PATH", "/tmp/sre_app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    last_login TEXT,
    login_count INTEGER DEFAULT 0,
    region TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL,
    merchant TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS api_logs (
    id INTEGER PRIMARY KEY,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_ms INTEGER NOT NULL,
    user_id INTEGER,
    ip_address TEXT NOT NULL,
    created_at TEXT NOT NULL,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(active);
CREATE INDEX IF NOT EXISTS idx_api_logs_endpoint ON api_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_api_logs_status ON api_logs(status_code);
"""

REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"]
STATUSES = ["active", "active", "active", "active", "suspended", "inactive"]
TX_STATUSES = ["completed", "completed", "completed", "pending", "failed", "refunded"]
MERCHANTS = [
    "Amazon", "Stripe", "Shopify", "PayPal", "Square", "Uber", "Netflix",
    "Spotify", "Apple", "Google", "Microsoft", "GitHub", "DigitalOcean",
]
ENDPOINTS = [
    "/api/v1/users", "/api/v1/transactions", "/api/v1/auth/login",
    "/api/v1/auth/refresh", "/api/v1/payments", "/api/v1/notifications",
    "/api/v1/webhooks", "/api/v1/health", "/api/v2/search",
]
METHODS = ["GET", "GET", "GET", "POST", "POST", "PUT", "DELETE"]
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "okhttp/4.12.0",
    "python-requests/2.31.0",
]


def setup_database(seed: int = 42):
    rng = random.Random(seed)
    base_time = datetime(2026, 3, 1, 0, 0, 0)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executescript(SCHEMA)

    # Check if already populated
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # Insert 10K users
    users = []
    for i in range(1, 10001):
        created = base_time + timedelta(days=rng.randint(0, 365))
        last_login = created + timedelta(days=rng.randint(0, 30))
        username = f"user_{i:05d}"
        email = f"{username}@{'gmail.com' if rng.random() < 0.6 else 'company.io'}"
        users.append((
            i, username, email,
            rng.choice(STATUSES),
            created.isoformat(),
            last_login.isoformat(),
            rng.randint(1, 500),
            rng.choice(REGIONS),
        ))

    cursor.executemany(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", users
    )

    # Insert 50K transactions
    txns = []
    for i in range(1, 50001):
        user_id = rng.randint(1, 10000)
        created = base_time + timedelta(
            days=rng.randint(0, 25),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        status = rng.choice(TX_STATUSES)
        processed = created + timedelta(seconds=rng.randint(1, 300)) if status != "pending" else None
        txns.append((
            i, user_id,
            round(rng.uniform(1.0, 5000.0), 2),
            rng.choice(["USD", "USD", "EUR", "GBP"]),
            status,
            rng.choice(MERCHANTS),
            created.isoformat(),
            processed.isoformat() if processed else None,
        ))

    cursor.executemany(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", txns
    )

    # Insert 5K sessions
    sessions = []
    for i in range(1, 5001):
        user_id = rng.randint(1, 10000)
        created = base_time + timedelta(days=rng.randint(0, 25), hours=rng.randint(0, 23))
        token = hashlib.sha256(f"session_{i}_{seed}".encode()).hexdigest()[:32]
        ip = f"{rng.randint(10, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        sessions.append((
            i, user_id, token, ip,
            rng.choice(USER_AGENTS),
            created.isoformat(),
            (created + timedelta(hours=24)).isoformat(),
            1 if rng.random() < 0.7 else 0,
        ))

    cursor.executemany(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", sessions
    )

    # Insert 20K API logs
    logs = []
    for i in range(1, 20001):
        created = base_time + timedelta(
            days=rng.randint(0, 25),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
            seconds=rng.randint(0, 59),
        )
        endpoint = rng.choice(ENDPOINTS)
        method = rng.choice(METHODS)
        status_code = rng.choices([200, 201, 400, 401, 403, 404, 500, 502, 503], weights=[60, 10, 5, 3, 2, 5, 3, 1, 1])[0]
        response_ms = rng.randint(5, 200) if status_code < 400 else rng.randint(100, 5000)
        ip = f"{rng.randint(10, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        error_msg = None
        if status_code >= 500:
            error_msg = rng.choice([
                "Internal server error", "Database connection timeout",
                "Redis connection refused", "Worker process unresponsive",
            ])
        logs.append((
            i, endpoint, method, status_code, response_ms,
            rng.randint(1, 10000) if rng.random() < 0.8 else None,
            ip, created.isoformat(), error_msg,
        ))

    cursor.executemany(
        "INSERT INTO api_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", logs
    )

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}: 10K users, 50K transactions, 5K sessions, 20K API logs")


if __name__ == "__main__":
    setup_database()
