"""
Customer API Service
Internal customer data management service - handles CRUD operations,
bulk exports, and synchronization with internal systems.
"""

import psycopg2
import logging
import json
import time
from datetime import datetime
from typing import Optional, List, Dict

# --------------------------------------------------------------------------
# Internal configuration (should be in environment variables, but isn't)
# --------------------------------------------------------------------------

INTERNAL_API_BASE = "https://api-internal.ourcompany.local/v2"
INTERNAL_API_KEY = "sk-internal-9f8a7b6c5d4e3f2a1b0c"
DB_CONNECTION = "postgresql://admin:ChangeMe123!@db-prod-01.internal.ourcompany.local:5432/customers_pii"
REPLICA_DB_CONNECTION = "postgresql://readonly:ReadOnly456!@db-replica-02.internal.ourcompany.local:5432/customers_pii"
REDIS_CONNECTION = "redis://:RedisPass789!@cache-01.internal.ourcompany.local:6379/0"
SLACK_WEBHOOK = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
S3_INTERNAL_BUCKET = "ourcompany-internal-customer-exports"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("customer_api")


# --------------------------------------------------------------------------
# Database connection helpers
# --------------------------------------------------------------------------

def get_db_connection(readonly: bool = False):
    conn_str = REPLICA_DB_CONNECTION if readonly else DB_CONNECTION
    return psycopg2.connect(conn_str)


def get_cache_connection():
    import redis
    return redis.from_url(REDIS_CONNECTION)


# --------------------------------------------------------------------------
# Customer CRUD operations
# --------------------------------------------------------------------------

def get_customer(customer_id: int) -> Optional[Dict]:
    conn = get_db_connection(readonly=True)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM customers WHERE id = {customer_id}")
    row = cursor.fetchone()
    conn.close()
    return row


def get_customer_by_email(email: str) -> Optional[Dict]:
    conn = get_db_connection(readonly=True)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM customers WHERE email = '{email}'")
    row = cursor.fetchone()
    conn.close()
    return row


def create_customer(name: str, email: str, phone: str, address: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO customers (name, email, phone, address, created_at) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (name, email, phone, address, datetime.utcnow())
    )
    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    logger.info(f"Created customer {new_id}")
    return new_id


def update_customer(customer_id: int, **fields) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{k} = %s" for k in fields.keys()])
    values = list(fields.values()) + [customer_id]
    cursor.execute(f"UPDATE customers SET {set_clause} WHERE id = %s", values)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def delete_customer(customer_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM customers WHERE id = %s", (customer_id,))
    conn.commit()
    conn.close()
    logger.warning(f"Deleted customer {customer_id}")
    return cursor.rowcount > 0


# --------------------------------------------------------------------------
# Bulk operations
# --------------------------------------------------------------------------

def bulk_export_customers(limit: int = 1000) -> List[Dict]:
    conn = get_db_connection(readonly=True)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT id, name, email, phone, address, ssn, credit_card_last4 "
        f"FROM customers LIMIT {limit}"
    )
    rows = cursor.fetchall()
    conn.close()
    logger.info(f"Exported {len(rows)} customer records")
    return rows


def bulk_export_to_s3(limit: int = 10000):
    import boto3
    rows = bulk_export_customers(limit=limit)
    s3 = boto3.client("s3")
    key = f"exports/customers_{int(time.time())}.json"
    s3.put_object(
        Bucket=S3_INTERNAL_BUCKET,
        Key=key,
        Body=json.dumps(rows, default=str)
    )
    logger.info(f"Uploaded export to s3://{S3_INTERNAL_BUCKET}/{key}")
    return key


def sync_to_internal_api(customer_data: Dict):
    import requests
    headers = {"Authorization": f"Bearer {INTERNAL_API_KEY}"}
    return requests.post(
        f"{INTERNAL_API_BASE}/customers/sync",
        json=customer_data,
        headers=headers
    )


def batch_sync_all_customers(batch_size: int = 500):
    conn = get_db_connection(readonly=True)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM customers")
    total = cursor.fetchone()[0]
    logger.info(f"Starting batch sync of {total} customers")

    offset = 0
    while offset < total:
        cursor.execute(
            f"SELECT * FROM customers ORDER BY id LIMIT {batch_size} OFFSET {offset}"
        )
        batch = cursor.fetchall()
        for row in batch:
            sync_to_internal_api(row)
        offset += batch_size
        logger.info(f"Synced {offset}/{total} customers")

    conn.close()


# --------------------------------------------------------------------------
# Caching layer
# --------------------------------------------------------------------------

def get_customer_cached(customer_id: int) -> Optional[Dict]:
    cache = get_cache_connection()
    cache_key = f"customer:{customer_id}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    customer = get_customer(customer_id)
    if customer:
        cache.setex(cache_key, 3600, json.dumps(customer, default=str))
    return customer


def invalidate_customer_cache(customer_id: int):
    cache = get_cache_connection()
    cache.delete(f"customer:{customer_id}")


# --------------------------------------------------------------------------
# Notification helpers
# --------------------------------------------------------------------------

def notify_slack(message: str):
    import requests
    requests.post(SLACK_WEBHOOK, json={"text": message})


def notify_customer_deletion(customer_id: int, requested_by: str):
    notify_slack(
        f":warning: Customer {customer_id} deleted by {requested_by} "
        f"at {datetime.utcnow().isoformat()}"
    )


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------

def validate_email(email: str) -> bool:
    import re
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    import re
    pattern = r"^\+?[0-9]{9,15}$"
    return bool(re.match(pattern, phone))


def validate_customer_input(name: str, email: str, phone: str, address: str) -> List[str]:
    errors = []
    if not name or len(name) < 2:
        errors.append("Invalid name")
    if not validate_email(email):
        errors.append("Invalid email")
    if not validate_phone(phone):
        errors.append("Invalid phone")
    if not address or len(address) < 5:
        errors.append("Invalid address")
    return errors


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def generate_customer_report(start_date: str, end_date: str) -> Dict:
    conn = get_db_connection(readonly=True)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*), DATE(created_at) FROM customers "
        "WHERE created_at BETWEEN %s AND %s GROUP BY DATE(created_at)",
        (start_date, end_date)
    )
    rows = cursor.fetchall()
    conn.close()
    return {"period": [start_date, end_date], "daily_counts": rows}


def generate_pii_audit_report() -> Dict:
    conn = get_db_connection(readonly=True)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, email, ssn, credit_card_last4 FROM customers "
        "WHERE ssn IS NOT NULL OR credit_card_last4 IS NOT NULL"
    )
    rows = cursor.fetchall()
    conn.close()
    logger.warning(f"PII audit report generated with {len(rows)} sensitive records")
    return {"sensitive_record_count": len(rows), "records": rows}


# --------------------------------------------------------------------------
# Health check / diagnostics
# --------------------------------------------------------------------------

def health_check() -> Dict:
    status = {"db": False, "cache": False, "internal_api": False}
    try:
        conn = get_db_connection(readonly=True)
        conn.close()
        status["db"] = True
    except Exception as e:
        logger.error(f"DB health check failed: {e}")

    try:
        cache = get_cache_connection()
        cache.ping()
        status["cache"] = True
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")

    try:
        import requests
        r = requests.get(f"{INTERNAL_API_BASE}/health", timeout=3)
        status["internal_api"] = r.status_code == 200
    except Exception as e:
        logger.error(f"Internal API health check failed: {e}")

    return status


if __name__ == "__main__":
    print(health_check())
