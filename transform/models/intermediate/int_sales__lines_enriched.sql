-- Sales lines joined to their header, conformed venue and product, with the local
-- trading date. Unmapped venues surface as location_key = 'UNMAPPED' and are
-- caught by tests/assert_every_pos_location_is_mapped.sql.

with lines as (
    select * from {{ ref('stg_pos__transaction_lines') }}
),

transactions as (
    select * from {{ ref('stg_pos__transactions') }}
),

locations as (
    select * from {{ ref('location_crosswalk') }}
),

products as (
    select * from {{ ref('stg_pos__products') }}
)

select
    l.transaction_line_key,
    l.transaction_id,
    l.line_id,
    t.transaction_status,
    t.sales_channel,
    t.staff_key,
    coalesce(loc.location_key, 'UNMAPPED')                        as location_key,
    l.sku                                                         as product_key,
    t.opened_at_utc,
    datetime(t.opened_at_utc, loc.timezone)                       as opened_at_local,
    {{ business_date('t.opened_at_utc', 'loc.timezone') }}        as business_date,
    l.quantity,
    l.unit_price,
    l.discount_amount,
    l.tax_amount,
    l.net_amount,
    round(l.quantity * p.unit_cost, 2)                            as estimated_cost_of_goods,
    greatest(t.source_updated_at, l.source_updated_at)            as source_updated_at
from lines l
inner join transactions t
    on t.transaction_id = l.transaction_id
left join locations loc
    on loc.pos_location_id = t.pos_location_id
left join products p
    on p.sku = l.sku
