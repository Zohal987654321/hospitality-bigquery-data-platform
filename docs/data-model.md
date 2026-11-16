# Data model

## Layers

| Dataset | Built by | Contents | Who can read |
|---|---|---|---|
| `raw_pos`, `raw_workforce`, `raw_inventory` | Python ingestion | Append-only. One row per record version: load metadata + JSON `payload`. Partitioned by `_ingested_at`, clustered by `_record_key`. | Pipeline only |
| `ops` | Python ingestion | `ingestion_watermarks`, `ingestion_runs`, `reconciliation_results` | Pipeline, engineers |
| `reference` | dbt seeds | Venue crosswalk, monthly budgets | Pipeline |
| `staging` | dbt (views) | Typed columns, latest version of each record | Engineers |
| `intermediate` | dbt (views) | Conformed keys, trading dates, paid hours | Engineers |
| `marts` | dbt (tables) | Star schema + daily scorecard | Analysts, BI |
| `ai` | dbt (views) | Plain-language views with column descriptions | AI agents, apps |

Why a JSON payload in raw: vendors add and rename fields without warning. Loading the
whole record means ingestion never breaks on schema drift, history is complete, and
staging decides which fields matter.

## Conformed identifiers

| Entity | Key | How it's made consistent |
|---|---|---|
| Venue | `location_key` (LOC-001…) | `seeds/location_crosswalk.csv` maps each system's own ID (POS, workforce, inventory) |
| Employee | `employee_key` | HMAC-SHA256 of the workforce employee ID; POS `staff_id` gets the same treatment, so they join |
| Product | `product_key` = SKU | SKU is shared by POS and inventory; normalised to upper case |
| Transaction | `transaction_id`, `transaction_line_key` | Source ID; line key is a hash of transaction + line |
| Period | `date_key` (YYYYMMDD), `business_date` | Trading date in venue-local time with a **4am cutoff** (a 1:30am sale belongs to the previous night). `dim_date` carries ISO weeks and the Australian fiscal year (July start). |

## Facts

| Model | Grain | Notes |
|---|---|---|
| `fct_sales_lines` | Transaction line | Incremental merge with a 3-day lookback. Keeps all statuses so a later void corrects the history. |
| `fct_labour_shifts` | Shift | Approved and pending; rejected excluded. `paid_hours` = length − unpaid break. |
| `fct_stock_counts` | Venue × product × count date | Weekly stocktake with stock value. |
| `mart_daily_location_performance` | Venue × trading day | Every venue gets every day in range, so zero-trade days are visible. |

## Metric definitions

| Metric | Definition |
|---|---|
| Net sales | Completed sales + refunds (negative), after discounts, **excluding GST**. Voids excluded. |
| Transaction count | Completed transactions only. |
| Average transaction value | Net sales / transaction count. |
| Labour cost % | Labour cost / net sales. |
| Sales per labour hour | Net sales / paid hours. |
| Budget (daily) | Monthly budget / days in month. |
| Estimated COGS | Quantity × current product unit cost (an estimate; not a stock-movement valuation). |

## Tests

- **Generic**: unique / not-null keys, relationships between every fact and its dimensions, accepted values, numeric ranges.
- **Reconciliation**: line items sum to transaction headers; daily mart totals equal the line-level fact.
- **Integrity**: every POS and workforce venue is mapped; no future-dated sales.
- **Unit test**: the 4am trading-day cutoff and paid-hours calculation.
- **Source freshness**: warns after 26h without new data (8 days for weekly inventory).
