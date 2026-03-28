"""
Collect real metrics from Redis, SQLite, filesystem, and processes.

All methods are safe to call even if the underlying service is unavailable.
Returns None on failure so the caller can fall back to simulated data.
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional


LOG_DIR = Path(os.environ.get("SRE_LOG_DIR", "/tmp/sre_logs"))
DB_PATH = os.environ.get("SRE_DB_PATH", "/tmp/sre_app.db")


class RealMetrics:

    def __init__(self):
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        try:
            import redis
            self._redis = redis.Redis(
                host="localhost", port=6379, decode_responses=True,
                socket_connect_timeout=1, socket_timeout=1,
            )
            self._redis.ping()
        except Exception:
            self._redis = None

    @property
    def redis_available(self) -> bool:
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            return False

    @property
    def sqlite_available(self) -> bool:
        return Path(DB_PATH).exists()

    def get_redis_metrics(self) -> Optional[dict]:
        if not self.redis_available:
            return None
        try:
            info = self._redis.info()
            return {
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "maxmemory_mb": round(info.get("maxmemory", 0) / 1024 / 1024, 2),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "evicted_keys": info.get("evicted_keys", 0),
                "used_memory_peak_mb": round(info.get("used_memory_peak", 0) / 1024 / 1024, 2),
                "total_keys": sum(
                    db.get("keys", 0)
                    for key, db in info.items()
                    if isinstance(db, dict) and key.startswith("db")
                ),
            }
        except Exception:
            return None

    def get_sqlite_metrics(self) -> Optional[dict]:
        if not self.sqlite_available:
            return None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM transactions")
            tx_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM sessions WHERE active = 1")
            active_sessions = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM api_logs WHERE status_code >= 500")
            error_count = cursor.fetchone()[0]

            cursor.execute("SELECT AVG(response_ms) FROM api_logs")
            avg_latency = cursor.fetchone()[0] or 0

            db_size = Path(DB_PATH).stat().st_size / 1024 / 1024

            conn.close()
            return {
                "total_users": user_count,
                "total_transactions": tx_count,
                "active_sessions": active_sessions,
                "error_count_5xx": error_count,
                "avg_response_ms": round(avg_latency, 1),
                "db_size_mb": round(db_size, 2),
            }
        except Exception:
            return None

    def get_process_list(self) -> Optional[list]:
        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "cmdline"]):
                try:
                    info = proc.info
                    mem_mb = info["memory_info"].rss / 1024 / 1024 if info["memory_info"] else 0
                    cmdline = " ".join(info["cmdline"][:3]) if info["cmdline"] else info["name"]
                    processes.append(
                        f"PID {info['pid']:<6d} {cmdline[:40]:<40s} "
                        f"{info['cpu_percent']:5.1f}% CPU  {mem_mb:6.0f}MB RAM"
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return processes[:30]
        except ImportError:
            return None
        except Exception:
            return None

    def get_log_tail(self, service: str, lines: int = 20) -> Optional[str]:
        log_file = LOG_DIR / f"{service}.log"
        if not log_file.exists():
            return None
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
                tail = all_lines[-lines:]
                if not tail:
                    return None
                return "".join(tail).rstrip()
        except Exception:
            return None

    def get_disk_usage(self) -> Optional[dict]:
        try:
            import shutil
            usage = shutil.disk_usage("/tmp")
            return {
                "total_gb": round(usage.total / 1024 / 1024 / 1024, 2),
                "used_gb": round(usage.used / 1024 / 1024 / 1024, 2),
                "free_gb": round(usage.free / 1024 / 1024 / 1024, 2),
                "used_pct": round(usage.used / usage.total * 100, 1),
            }
        except Exception:
            return None
