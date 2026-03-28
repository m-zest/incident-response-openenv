"""
Chaos engine for injecting real infrastructure failures.

Each injection is safe, reversible, and contained to /tmp.
All methods handle missing dependencies gracefully.
"""

import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional


DB_PATH = os.environ.get("SRE_DB_PATH", "/tmp/sre_app.db")
LOG_DIR = Path(os.environ.get("SRE_LOG_DIR", "/tmp/sre_logs"))
CHAOS_FLAG = Path("/tmp/sre_chaos_active")
CHAOS_SCENARIO_FILE = Path("/tmp/sre_chaos_scenario")


class ChaosEngine:

    def __init__(self):
        self._redis = None
        self._chaos_pids: list[int] = []
        self._held_connections: list = []
        self._temp_files: list[Path] = []
        self._active_scenario: str = ""
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

    def inject(self, scenario_id: str):
        self.cleanup()
        self._active_scenario = scenario_id

        CHAOS_FLAG.touch()
        CHAOS_SCENARIO_FILE.write_text(scenario_id)

        injector = getattr(self, f"_inject_{scenario_id}", None)
        if injector:
            injector()

    def cleanup(self):
        # Kill spawned chaos processes
        for pid in self._chaos_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        self._chaos_pids.clear()

        # Release held database connections
        for conn in self._held_connections:
            try:
                conn.close()
            except Exception:
                pass
        self._held_connections.clear()

        # Flush chaos Redis keys
        if self.redis_available:
            try:
                pipe = self._redis.pipeline()
                for key in self._redis.scan_iter("leak:*"):
                    pipe.delete(key)
                for key in self._redis.scan_iter("chaos:*"):
                    pipe.delete(key)
                self._redis.delete("chaos:backlog")
                pipe.execute()
            except Exception:
                pass

        # Remove temp files
        for f in self._temp_files:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        self._temp_files.clear()

        # Remove chaos flags
        CHAOS_FLAG.unlink(missing_ok=True)
        CHAOS_SCENARIO_FILE.unlink(missing_ok=True)
        self._active_scenario = ""

    # ── Scenario-specific injections ──────────────────────────────────────

    def _inject_easy_disk_full(self):
        fill_path = Path("/tmp/sre_disk_fill")
        try:
            with open(fill_path, "wb") as f:
                f.write(b"\0" * (10 * 1024 * 1024))  # 10MB fill file
            self._temp_files.append(fill_path)
        except Exception:
            pass

    def _inject_easy_memory_leak(self):
        if not self.redis_available:
            return
        try:
            pipe = self._redis.pipeline()
            for i in range(5000):
                pipe.set(f"leak:{i}", "x" * 100)
            pipe.execute()
        except Exception:
            pass

    def _inject_easy_service_crash(self):
        pass

    def _inject_easy_bad_deploy(self):
        pass

    def _inject_easy_cert_expired(self):
        pass

    def _inject_medium_cache_failure(self):
        if not self.redis_available:
            return
        try:
            pipe = self._redis.pipeline()
            for i in range(10000):
                pipe.set(f"chaos:fill:{i}", "x" * 512)
            pipe.execute()
        except Exception:
            pass

    def _inject_medium_db_pool_exhaustion(self):
        if not Path(DB_PATH).exists():
            return
        try:
            for _ in range(20):
                conn = sqlite3.connect(DB_PATH, timeout=1)
                conn.execute("BEGIN EXCLUSIVE")
                self._held_connections.append(conn)
        except Exception:
            pass

    def _inject_medium_queue_backlog(self):
        if not self.redis_available:
            return
        try:
            pipe = self._redis.pipeline()
            for i in range(50000):
                pipe.rpush("chaos:backlog", f"job_{i}")
            pipe.execute()
        except Exception:
            pass

    def _inject_medium_dns_failure(self):
        pass

    def _inject_hard_crypto_mining(self):
        try:
            proc = subprocess.Popen(
                ["python3", "-c",
                 "import time, math\n"
                 "while True:\n"
                 "    sum(math.sqrt(i) for i in range(100000))\n"
                 "    time.sleep(0.01)\n"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._chaos_pids.append(proc.pid)
        except Exception:
            pass

    def _inject_hard_cascading_config(self):
        pass

    def _inject_hard_ddos_vs_traffic(self):
        pass

    def _inject_expert_split_brain(self):
        replica_path = Path("/tmp/sre_replica.db")
        try:
            if Path(DB_PATH).exists():
                import shutil
                shutil.copy2(DB_PATH, replica_path)
                self._temp_files.append(replica_path)

                conn = sqlite3.connect(str(replica_path))
                conn.execute(
                    "UPDATE transactions SET amount = amount + 100 "
                    "WHERE id IN (SELECT id FROM transactions ORDER BY RANDOM() LIMIT 50)"
                )
                conn.commit()
                conn.close()
        except Exception:
            pass

    def _inject_expert_supply_chain(self):
        pass
