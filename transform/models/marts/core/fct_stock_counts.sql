-- Grain: one row per venue, product and count date (weekly stocktake).
select
    s.stock_count_key,
    coalesce(loc.location_key, 'UNMAPPED')                    as location_key,
    s.sku                                                     as product_key,
    cast(format_date('%Y%m%d', s.counted_on) as int64)        as date_key,
    s.counted_on,
    s.quantity_on_hand,
    s.unit_cost,
    round(s.quantity_on_hand * s.unit_cost, 2)                as stock_value,
    s.source_file
from {{ ref('stg_inventory__stock_counts') }} s
left join {{ ref('location_crosswalk') }} loc
    on loc.inventory_location_code = s.inventory_location_code
