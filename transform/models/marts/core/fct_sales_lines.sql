{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key='transaction_line_key',
        partition_by={'field': 'business_date', 'data_type': 'date', 'granularity': 'day'},
        cluster_by=['location_key', 'product_key'],
        on_schema_change='append_new_columns'
    )
}}

-- Grain: one row per POS transaction line (all statuses; voids filtered in marts so a
-- transaction voided after the fact is corrected by the merge).

select
    transaction_line_key,
    transaction_id,
    line_id,
    location_key,
    product_key,
    cast(format_date('%Y%m%d', business_date) as int64) as date_key,
    business_date,
    opened_at_local,
    transaction_status,
    sales_channel,
    staff_key,
    quantity,
    unit_price,
    discount_amount,
    tax_amount,
    net_amount,
    estimated_cost_of_goods,
    source_updated_at
from {{ ref('int_sales__lines_enriched') }}

{% if is_incremental() %}
where source_updated_at >= (
    select timestamp_sub(max(source_updated_at), interval {{ var('incremental_lookback_days') }} day)
    from {{ this }}
)
{% endif %}
