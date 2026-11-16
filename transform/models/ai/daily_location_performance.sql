-- Agent-facing view. Plain column names, no keys an agent could misuse, and
-- descriptions persisted to BigQuery so MCP tools can read the definitions.
select
    location_name,
    business_date,
    format_date('%A', business_date)  as day_of_week,
    net_sales,
    refunds,
    transaction_count,
    avg_transaction_value,
    items_sold,
    labour_hours,
    labour_cost,
    labour_cost_pct,
    sales_per_labour_hour,
    staff_rostered,
    budget_net_sales,
    variance_to_budget,
    estimated_cogs_pct
from {{ ref('mart_daily_location_performance') }}
