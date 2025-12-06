# db_functions.py
"""
BigQuery helper functions for local / VS Code use.

Requirements:
  pip install google-cloud-bigquery

Authentication options (pick one):
  1) Service account JSON (recommended):
     export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
     OR pass service_account_json="/path/to/key.json" to connect_to_db()

  2) Application Default Credentials (dev):
     gcloud auth application-default login
     then call connect_to_db() normally.
"""

import os
from typing import Dict, List, Any, Optional

from google.cloud import bigquery
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

# Default project/dataset — change if needed
DEFAULT_PROJECT = "sqlproject-480314"
DEFAULT_DATASET = "sql_dataset"
DEFAULT_LOCATION = "US"


def connect_to_db(
    project_id: str = DEFAULT_PROJECT,
    dataset: str = DEFAULT_DATASET,
    location: str = DEFAULT_LOCATION,
    service_account_json: Optional[str] = None,
) -> bigquery.Client:
    """
    Connect to BigQuery and return a client.
    If service_account_json is provided, it will be set as GOOGLE_APPLICATION_CREDENTIALS.
    Otherwise the client will use ADC or environment variable.
    """
    if service_account_json:
        if not os.path.exists(service_account_json):
            raise FileNotFoundError(f"Service account file not found: {service_account_json}")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_json

    client = bigquery.Client(project=project_id, location=location)
    # attach dataset name for convenience
    client._default_dataset = dataset  # non-standard, but useful internally
    return client


# -------------------------
# Utility: run scalar queries
# -------------------------
def run_scalar_query(client: bigquery.Client, sql: str, job_config: Optional[QueryJobConfig] = None) -> Any:
    job = client.query(sql, job_config=job_config)
    df = job.result().to_dataframe()
    if df.empty:
        return None
    return df.iloc[0, 0]


# -------------------------
# Basic dashboard info
# -------------------------
def get_basic_info(client: bigquery.Client, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> Dict[str, Any]:
    prefix = f"`sqlproject-480314.sql_dataset`"
    queries = {
        "Total Suppliers": f"SELECT COUNT(*) AS count FROM {prefix}.suppliers",
        "Total Products": f"SELECT COUNT(*) AS count FROM {prefix}.products",
        "Total Categories Dealing": f"SELECT COUNT(DISTINCT category) AS count FROM {prefix}.products",
        "Total Sale Value (Last 3 Months)": f"""
            SELECT ROUND(SUM(ABS(se.change_quantity) * p.price), 2) AS total_sale
            FROM {prefix}.stock_entries se
            JOIN {prefix}.products p ON se.product_id = p.product_id
            WHERE se.change_type = 'Sale'
              AND se.entry_date >= (
                SELECT DATE_SUB(MAX(entry_date), INTERVAL 3 MONTH) FROM {prefix}.stock_entries
              )
        """,
        "Total Restock Value (Last 3 Months)": f"""
            SELECT ROUND(SUM(se.change_quantity * p.price), 2) AS total_restock
            FROM {prefix}.stock_entries se
            JOIN {prefix}.products p ON se.product_id = p.product_id
            WHERE se.change_type = 'Restock'
              AND se.entry_date >= (
                SELECT DATE_SUB(MAX(entry_date), INTERVAL 3 MONTH) FROM {prefix}.stock_entries
              )
        """,
        "Below Reorder & No Pending Reorders": f"""
            SELECT COUNT(*) AS below_reorder
            FROM {prefix}.products p
            WHERE p.stock_quantity < p.reorder_level
              AND p.product_id NOT IN (
                SELECT DISTINCT product_id FROM {prefix}.reorders WHERE status = 'Pending'
              )
        """,
    }

    results = {}
    for label, sql in queries.items():
        try:
            results[label] = run_scalar_query(client, sql)
        except Exception as e:
            results[label] = f"ERROR: {type(e).__name__}: {e}"
    return results


# -------------------------
# Additional tables
# -------------------------
def get_additional_tables(client: bigquery.Client, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> Dict[str, List[Dict[str, Any]]]:
    prefix = f"`sqlproject-480314.sql_dataset`"
    queries = {
        "Suppliers Contact Details": f"SELECT supplier_name, contact_name, email, phone FROM {prefix}.suppliers",
        "Products with Supplier and Stock": f"""
            SELECT p.product_name, s.supplier_name, p.stock_quantity, p.reorder_level
            FROM {prefix}.products p
            JOIN {prefix}.suppliers s ON p.supplier_id = s.supplier_id
            ORDER BY p.product_name ASC
        """,
        "Products Needing Reorder": f"SELECT product_id, product_name, stock_quantity, reorder_level FROM {prefix}.products WHERE stock_quantity <= reorder_level",
    }

    tables = {}
    for label, sql in queries.items():
        try:
            job = client.query(sql)
            rows = job.result()
            tables[label] = [dict(row) for row in rows]
        except Exception as e:
            tables[label] = f"ERROR: {type(e).__name__}: {e}"
    return tables


# -------------------------
# Categories / Suppliers / Products
# -------------------------
def get_categories(client: bigquery.Client, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> List[str]:
    sql = f"SELECT DISTINCT category FROM `sqlproject-480314.sql_dataset.products` ORDER BY category ASC"
    job = client.query(sql)
    return [row.category for row in job.result()]


def get_suppliers(client: bigquery.Client, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> List[Dict[str, Any]]:
    sql = f"SELECT supplier_id, supplier_name FROM `sqlproject-480314.sql_dataset.suppliers` ORDER BY supplier_name ASC"
    job = client.query(sql)
    return [{"supplier_id": row.supplier_id, "supplier_name": row.supplier_name} for row in job.result()]


def get_all_products(client: bigquery.Client, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> List[Dict[str, Any]]:
    sql = f"SELECT product_id, product_name FROM `sqlproject-480314.sql_dataset.products` ORDER BY product_name"
    job = client.query(sql)
    return [{"product_id": row.product_id, "product_name": row.product_name} for row in job.result()]


def get_product_history(client: bigquery.Client, product_id: int, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> List[Dict[str, Any]]:
    sql = f"SELECT * FROM `sqlproject-480314.sql_dataset.product_inventory_history` WHERE product_id = @pid ORDER BY record_date DESC"
    job_config = QueryJobConfig(query_parameters=[ScalarQueryParameter("pid", "INT64", product_id)])
    job = client.query(sql, job_config=job_config)
    return [dict(row) for row in job.result()]


# -------------------------
# Add new product: Python implementation (emulates MySQL proc)
# -------------------------
def add_new_manual_id(
    client: bigquery.Client,
    p_name: str,
    p_category: str,
    p_price: float,
    p_stock: int,
    p_reorder: int,
    p_supplier: int,
    project: str = DEFAULT_PROJECT,
    dataset: str = DEFAULT_DATASET,
) -> Dict[str, int]:
    """
    Emulate AddNewProductManualID procedure in Python:
      - compute next product_id, insert into products
      - compute next shipment_id, insert into shipments
      - compute next entry_id, insert into stock_entries
    Returns inserted ids.
    Note: BigQuery DML is not transactional like MySQL; consider Cloud SQL for transactional needs.
    """
    prefix = f"`sqlproject-480314.sql_dataset`"

    # 1) new_prod_id
    new_prod_id = int(run_scalar_query(client, f"SELECT IFNULL(MAX(product_id), 0) + 1 AS new_id FROM sql_dataset.products"))

    # insert product (parameterized)
    insert_product_sql = f"""
        INSERT INTO sql_dataset.products
        (product_id, product_name, category, price, stock_quantity, reorder_level, supplier_id)
        VALUES (@pid, @pname, @pcat, @pprice, @pstock, @preorder, @psupplier)
    """
    config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("pid", "INT64", new_prod_id),
            ScalarQueryParameter("pname", "STRING", p_name),
            ScalarQueryParameter("pcat", "STRING", p_category),
            ScalarQueryParameter("pprice", "NUMERIC", p_price),
            ScalarQueryParameter("pstock", "INT64", p_stock),
            ScalarQueryParameter("preorder", "INT64", p_reorder),
            ScalarQueryParameter("psupplier", "INT64", p_supplier),
        ]
    )
    client.query(insert_product_sql, job_config=config).result()

    # 2) new_shipment_id
    new_shipment_id = int(run_scalar_query(client, f"SELECT IFNULL(MAX(shipment_id), 0) + 1 AS new_id FROM sql_dataset.shipments"))

    insert_shipment_sql = f"""
        INSERT INTO sql_dataset.shipments
        (shipment_id, product_id, supplier_id, quantity_received, shipment_date)
        VALUES (@sid, @pid, @supp, @qty, CURRENT_DATE())
    """
    config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("sid", "INT64", new_shipment_id),
            ScalarQueryParameter("pid", "INT64", new_prod_id),
            ScalarQueryParameter("supp", "INT64", p_supplier),
            ScalarQueryParameter("qty", "INT64", p_stock),
        ]
    )
    client.query(insert_shipment_sql, job_config=config).result()

    # 3) new_entry_id
    new_entry_id = int(run_scalar_query(client, f"SELECT IFNULL(MAX(entry_id), 0) + 1 AS new_id FROM sql_dataset.stock_entries"))

    insert_entry_sql = f"""
        INSERT INTO sql_dataset.stock_entries
        (entry_id, product_id, change_quantity, change_type, entry_date)
        VALUES (@eid, @pid, @chg, 'Restock', CURRENT_DATE())
    """
    config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("eid", "INT64", new_entry_id),
            ScalarQueryParameter("pid", "INT64", new_prod_id),
            ScalarQueryParameter("chg", "INT64", p_stock),
        ]
    )
    client.query(insert_entry_sql, job_config=config).result()

    return {"product_id": new_prod_id, "shipment_id": new_shipment_id, "entry_id": new_entry_id}


# -------------------------
# Place reorder (emulates MySQL insert-select)
# -------------------------
def place_reorder(client: bigquery.Client, product_id: int, reorder_quantity: int, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> int:
    prefix = f"`sqlproject-480314.sql_dataset`"
    new_reorder_id = int(run_scalar_query(client, f"SELECT IFNULL(MAX(reorder_id), 0) + 1 FROM sql_dataset.reorders"))

    sql = f"""
        INSERT INTO sql_dataset.reorders (reorder_id, product_id, reorder_quantity, reorder_date, status)
        VALUES (@rid, @pid, @qty, CURRENT_DATE(), 'Ordered')
    """
    config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("rid", "INT64", new_reorder_id),
            ScalarQueryParameter("pid", "INT64", product_id),
            ScalarQueryParameter("qty", "INT64", reorder_quantity),
        ]
    )
    client.query(sql, job_config=config).result()
    return new_reorder_id


# -------------------------
# Pending reorders and mark received
# -------------------------
def get_pending_reorders(client: bigquery.Client, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> List[Dict[str, Any]]:
    sql = f"""
        SELECT r.reorder_id, p.product_name
        FROM `sqlproject-480314.sql_dataset.reorders` r
        JOIN `sqlproject-480314.sql_dataset.products` p ON r.product_id = p.product_id
        WHERE r.status = 'Pending'
    """
    job = client.query(sql)
    return [{"reorder_id": row.reorder_id, "product_name": row.product_name} for row in job.result()]


def mark_reorder_as_received(client: bigquery.Client, reorder_id: int, project: str = DEFAULT_PROJECT, dataset: str = DEFAULT_DATASET) -> None:
    """
    Updates the reorder status to 'Received'. If you also need to update product stock,
    implement additional logic here (insert into stock_entries etc).
    """
    sql = f"UPDATE `sqlproject-480314.sql_dataset.reorders` SET status = 'Received' WHERE reorder_id = @rid"
    config = QueryJobConfig(query_parameters=[ScalarQueryParameter("rid", "INT64", reorder_id)])
    client.query(sql, job_config=config).result()


# -------------------------
# Example CLI test (only run when executed directly)
# -------------------------
if __name__ == "__main__":
    client = connect_to_db()  # uses ADC or GOOGLE_APPLICATION_CREDENTIALS
    print("Connected to BigQuery:", client.project)

    # Basic info
    print("Basic info:", get_basic_info(client))

    # Show a couple of tables
    print("Additional tables keys:", list(get_additional_tables(client).keys()))
