"""
Background worker that writes realistic service logs to /tmp/sre_logs/.

Runs continuously, producing normal operational logs. When a chaos trigger
file exists (/tmp/sre_chaos_active), switches to error-pattern logs
matching the active scenario.
"""

import os
import time
import random
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(os.environ.get("SRE_LOG_DIR", "/tmp/sre_logs"))
CHAOS_FLAG = Path("/tmp/sre_chaos_active")
CHAOS_SCENARIO_FILE = Path("/tmp/sre_chaos_scenario")

SERVICES = ["api-gateway", "user-service", "payment-service", "worker-queue"]

NORMAL_LOGS = {
    "api-gateway": [
        "INFO  Request processed: GET /api/v1/health 200 {latency}ms",
        "INFO  Request processed: POST /api/v1/users 201 {latency}ms",
        "INFO  Request processed: GET /api/v1/transactions 200 {latency}ms",
        "DEBUG Connection pool: {conns}/500 active",
        "INFO  Rate limiter: {rps} req/s (limit: 10000)",
    ],
    "user-service": [
        "INFO  User lookup: user_{uid} in {latency}ms",
        "INFO  Session validated: token_{tid}",
        "INFO  Auth check passed for user_{uid}",
        "DEBUG Cache hit ratio: {ratio}%",
    ],
    "payment-service": [
        "INFO  Transaction processed: ${amount} for user_{uid}",
        "INFO  Payment gateway response: 200 in {latency}ms",
        "DEBUG Fraud check passed: score={score}",
        "INFO  Webhook delivered to merchant in {latency}ms",
    ],
    "worker-queue": [
        "INFO  Job completed: email_notification in {latency}ms",
        "INFO  Job completed: report_generation in {latency}ms",
        "INFO  Queue depth: {depth} jobs pending",
        "DEBUG Worker pool: {workers}/8 active",
    ],
}

CHAOS_LOGS = {
    "easy_disk_full": {
        "api-gateway": [
            "ERROR  Failed to write access log: No space left on device",
            "WARN   Log buffer backing up, {depth} entries queued",
        ],
    },
    "easy_memory_leak": {
        "user-service": [
            "WARN   Heap usage: {mem}MB / 512MB ({pct}%)",
            "ERROR  GC pause: {latency}ms (exceeds 200ms threshold)",
            "WARN   Object count growing: {count} live objects",
        ],
    },
    "easy_service_crash": {
        "worker-queue": [
            "ERROR  Worker process exited with signal 11 (SIGSEGV)",
            "WARN   Job queue backing up: {depth} unprocessed",
            "ERROR  Failed to dequeue job: worker unavailable",
        ],
    },
    "medium_cache_failure": {
        "payment-service": [
            "WARN   Cache miss for session_{tid}, falling back to DB",
            "ERROR  Redis ENOMEM: maxmemory reached, evicting keys",
            "WARN   Cache hit ratio dropped to {ratio}%",
        ],
    },
    "medium_db_pool_exhaustion": {
        "api-gateway": [
            "ERROR  Database connection timeout after 30000ms",
            "WARN   Connection pool exhausted: {conns}/{conns} in use",
            "ERROR  Failed to acquire connection, request queued",
        ],
        "user-service": [
            "ERROR  Query timeout: SELECT * FROM users WHERE id = {uid}",
            "WARN   Slow query detected: {latency}ms (threshold: 500ms)",
        ],
    },
    "medium_queue_backlog": {
        "worker-queue": [
            "ERROR  Queue depth critical: {depth} pending (limit: 1000)",
            "WARN   Worker starvation: no jobs completed in 30s",
            "ERROR  Dead letter queue growing: {dead} failed jobs",
        ],
    },
    "hard_crypto_mining": {
        "payment-service": [
            "WARN   CPU spike detected: {cpu}% utilization",
            "ERROR  Unexpected outbound connection to {ext_ip}:{port}",
            "WARN   Process [jvm-gc-thread-4] consuming {cpu}% CPU",
        ],
    },
    "hard_ddos_vs_traffic": {
        "api-gateway": [
            "WARN   Request rate: {rps}/s (10x normal baseline)",
            "ERROR  Connection limit reached: {conns}/500",
            "WARN   Source IP concentration: {pct}% from single /24 subnet",
        ],
    },
    "expert_split_brain": {
        "api-gateway": [
            "ERROR  Inconsistent read: user_{uid} balance differs between replicas",
            "WARN   Replication lag: {latency}ms (primary vs replica)",
        ],
    },
    "expert_supply_chain": {
        "user-service": [
            "WARN   Unusual DNS queries from node module: analytics-helper",
            "ERROR  Outbound POST to {ext_ip} with encoded payload",
        ],
        "payment-service": [
            "ERROR  Environment variable access from untrusted module",
            "WARN   Token exfiltration attempt detected in dependency",
        ],
    },
}


def write_log(service: str, message: str):
    log_file = LOG_DIR / f"{service}.log"
    timestamp = datetime.utcnow().strftime("[%Y-%m-%dT%H:%M:%SZ]")
    with open(log_file, "a") as f:
        f.write(f"{timestamp} {message}\n")


def format_log(template: str, rng: random.Random) -> str:
    return template.format(
        latency=rng.randint(5, 350),
        conns=rng.randint(50, 480),
        rps=rng.randint(100, 8000),
        uid=rng.randint(1, 10000),
        tid=rng.randint(1, 5000),
        amount=round(rng.uniform(5, 2000), 2),
        score=round(rng.uniform(0.01, 0.95), 2),
        depth=rng.randint(5, 500),
        workers=rng.randint(4, 8),
        ratio=rng.randint(85, 99),
        mem=rng.randint(200, 510),
        pct=rng.randint(60, 99),
        count=rng.randint(50000, 500000),
        cpu=rng.randint(70, 99),
        ext_ip=f"{rng.randint(45, 185)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}",
        port=rng.choice([443, 8443, 4444, 9999]),
        dead=rng.randint(10, 200),
    )


def get_active_scenario() -> str:
    if CHAOS_SCENARIO_FILE.exists():
        return CHAOS_SCENARIO_FILE.read_text().strip()
    return ""


def run():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    # Clear old logs on startup
    for service in SERVICES:
        log_file = LOG_DIR / f"{service}.log"
        if log_file.exists():
            log_file.write_text("")

    while True:
        chaos_active = CHAOS_FLAG.exists()
        scenario_id = get_active_scenario() if chaos_active else ""

        for service in SERVICES:
            # Normal log
            templates = NORMAL_LOGS.get(service, [])
            if templates:
                msg = format_log(rng.choice(templates), rng)
                write_log(service, msg)

            # Chaos-injected error logs
            if chaos_active and scenario_id:
                error_templates = CHAOS_LOGS.get(scenario_id, {}).get(service, [])
                if error_templates:
                    msg = format_log(rng.choice(error_templates), rng)
                    write_log(service, msg)

        time.sleep(2)


if __name__ == "__main__":
    run()
