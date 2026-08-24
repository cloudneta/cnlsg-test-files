import psycopg2

INTERNAL_API_BASE = "https://api-internal.ourcompany.local/v2"
DB_CONNECTION = "postgresql://admin:ChangeMe123!@db-prod-01.internal.ourcompany.local:5432/customers_pii"


def get_customer(customer_id):
    conn = psycopg2.connect(DB_CONNECTION)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM customers WHERE id = {customer_id}")
    return cursor.fetchone()


def sync_to_internal_api(customer_data):
    import requests
    return requests.post(f"{INTERNAL_API_BASE}/customers/sync", json=customer_data)


def bulk_export_customers(limit=1000):
    conn = psycopg2.connect(DB_CONNECTION)
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, name, email, phone, address FROM customers LIMIT {limit}")
    return cursor.fetchall()
