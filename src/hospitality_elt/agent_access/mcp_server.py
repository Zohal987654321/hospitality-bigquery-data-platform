"""Read-only MCP server that gives AI agents governed access to the ``ai`` dataset.

Tools
-----
list_tables          tables/views the agent may use, with their descriptions
describe_table       column names, types and business definitions
daily_performance    parameterised sales vs labour vs budget lookup (no SQL needed)
run_query            guarded SELECT over the ``ai`` dataset, with a byte cap

Descriptions come from BigQuery itself: dbt ``persist_docs`` writes model and column
docs into table metadata, so the agent reads the same definitions as analysts.

Run:  python -m hospitality_elt.agent_access.mcp_server          (stdio)
      MCP_TRANSPORT=streamable-http python -m ...                 (Cloud Run)
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from mcp.server.mcpserver import MCPServer

from hospitality_elt.agent_access.sql_guard import UnsafeQueryError, check_query

PROJECT = os.environ.get("GCP_PROJECT_ID", "")
DATASET = os.environ.get("AI_DATASET", "ai")
MAX_BYTES = int(os.environ.get("AGENT_MAX_BYTES_BILLED", str(2 * 1024**3)))  # 2 GiB
MAX_ROWS = 500

server = MCPServer(
    name="hospitality-warehouse",
    instructions=(
        "Read-only access to curated hospitality analytics in BigQuery. "
        "Start with list_tables and describe_table. Business dates use a 4am trading-day "
        "cutoff in each venue's local time. Money is AUD excluding GST. Employee data is "
        "pseudonymised; never try to identify individuals."
    ),
)

_client = None


def _bq():
    global _client
    if _client is None:
        from google.cloud import bigquery

        _client = bigquery.Client(project=PROJECT or None)
    return _client


def _run(sql: str, params: list[Any] | None = None, max_rows: int = MAX_ROWS) -> list[dict]:
    from google.cloud import bigquery

    cfg = bigquery.QueryJobConfig(
        query_parameters=params or [],
        maximum_bytes_billed=MAX_BYTES,
        use_query_cache=True,
        labels={"caller": "mcp-agent"},
    )
    rows = _bq().query(sql, job_config=cfg).result(max_results=max_rows)
    return [{k: (str(v) if v is not None else None) for k, v in dict(r).items()} for r in rows]


@server.tool()
def list_tables() -> list[dict]:
    """List the curated tables and views available for analysis, with descriptions."""
    return _run(
        f"""
        select t.table_name, t.table_type, o.option_value as description
        from `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.TABLES` t
        left join `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.TABLE_OPTIONS` o
          on o.table_name = t.table_name and o.option_name = 'description'
        order by t.table_name
        """
    )


@server.tool()
def describe_table(table_name: str) -> list[dict]:
    """Return columns, data types and business definitions for one table."""
    from google.cloud import bigquery

    return _run(
        f"""
        select column_name, data_type, description
        from `{PROJECT}.{DATASET}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
        where table_name = @table_name
        order by column_name
        """,
        [bigquery.ScalarQueryParameter("table_name", "STRING", table_name)],
    )


@server.tool()
def daily_performance(
    start_date: str, end_date: str, location_name: str | None = None
) -> list[dict]:
    """Net sales, transactions, labour cost %, and budget variance per venue per day.

    Dates are ISO (YYYY-MM-DD), inclusive. Omit location_name for all venues.
    """
    from google.cloud import bigquery

    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if (end - start).days > 400:
        raise ValueError("Please request at most ~13 months at a time.")
    return _run(
        f"""
        select *
        from `{PROJECT}.{DATASET}.daily_location_performance`
        where business_date between @start and @end
          and (@location is null or lower(location_name) = lower(@location))
        order by business_date, location_name
        """,
        [
            bigquery.ScalarQueryParameter("start", "DATE", start),
            bigquery.ScalarQueryParameter("end", "DATE", end),
            bigquery.ScalarQueryParameter("location", "STRING", location_name),
        ],
    )


@server.tool()
def run_query(sql: str, max_rows: int = 200) -> dict:
    """Run a read-only SELECT against the `ai` dataset (max 500 rows, byte-capped)."""
    from google.cloud import bigquery

    try:
        cleaned = check_query(sql, {DATASET})
    except UnsafeQueryError as exc:
        return {"error": str(exc)}
    dry = _bq().query(
        cleaned, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    )
    if dry.total_bytes_processed > MAX_BYTES:
        return {"error": f"Query would scan {dry.total_bytes_processed:,} bytes; add filters."}
    rows = _run(cleaned, max_rows=min(max_rows, MAX_ROWS))
    return {"rows": rows, "row_count": len(rows), "bytes_scanned": dry.total_bytes_processed}


if __name__ == "__main__":
    server.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))  # type: ignore[arg-type]
