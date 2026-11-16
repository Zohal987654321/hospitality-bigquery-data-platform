# AI agent access

AI agents and internal apps get governed, read-only access to curated data through the
`ai` dataset and an MCP server.

## The `ai` dataset

- Views over the marts with plain column names (`location_name`, not `location_key`).
- No employee-level rows: labour is aggregated per venue per day.
- Every table and column description is written for an LLM reader (units, sign
  conventions, grain) in `transform/models/ai/_ai.yml`. dbt `persist_docs` writes them
  into BigQuery metadata, so the agent reads the same definitions analysts see.

## MCP server

`src/hospitality_elt/agent_access/mcp_server.py` exposes four tools:

| Tool | Purpose |
|---|---|
| `list_tables` | What's available, with descriptions |
| `describe_table` | Columns, types and business definitions |
| `daily_performance(start_date, end_date, location_name?)` | Parameterised scorecard lookup — no SQL needed for the most common questions |
| `run_query(sql, max_rows)` | Read-only SELECT over `ai`, for anything else |

Guardrails, from strongest to weakest:
1. **IAM** — runs as `sa-hosp-agent`, which can read only the `ai` dataset.
2. **Cost cap** — every job has `maximum_bytes_billed`; queries are dry-run first and
   refused if they would scan too much.
3. **SQL guard** — single SELECT statements only, no DML/DDL, only tables in `ai`
   (`sql_guard.py`, covered by tests). Gives the agent a clear error to correct itself.
4. **Row limit** — at most 500 rows returned.

Jobs are labelled `caller=mcp-agent` so agent usage and cost can be tracked separately.

## Running it

Local (stdio), e.g. for Claude Desktop or another MCP client:

```json
{
  "mcpServers": {
    "hospitality-warehouse": {
      "command": "python",
      "args": ["-m", "hospitality_elt.agent_access.mcp_server"],
      "env": { "GCP_PROJECT_ID": "my-hospitality-prod" }
    }
  }
}
```

Hosted: deploy the same image to Cloud Run with
`MCP_TRANSPORT=streamable-http`, service account `sa-hosp-agent`, and IAM-authenticated
invocation (no public access).

Example questions an agent can answer:
- "Which venue had the highest labour cost % last week, and on which days?"
- "How are we tracking against November budget by venue?"
- "Top 5 products by net sales at Riverfront Bar on Saturdays this month."
