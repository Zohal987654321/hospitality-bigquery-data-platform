-- SKU is the conformed product identifier: the POS and the inventory system both use it.
select
    sku                 as product_key,
    pos_product_id,
    product_name,
    product_category,
    list_price,
    unit_cost,
    safe_divide(list_price - unit_cost, list_price) as gross_margin_pct
from {{ ref('stg_pos__products') }}
