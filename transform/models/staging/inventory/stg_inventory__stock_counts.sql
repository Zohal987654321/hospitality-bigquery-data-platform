with latest as (
    {{ latest_version(source('raw_inventory', 'stock_counts')) }}
)

select
    {{ surrogate_key(["json_value(payload, '$.location_code')", "json_value(payload, '$.sku')",
                      "json_value(payload, '$.counted_on')"]) }}   as stock_count_key,
    upper(trim({{ j_str('location_code') }}))                       as inventory_location_code,
    upper(trim({{ j_str('sku') }}))                                 as sku,
    safe_cast({{ j_str('counted_on') }} as date)                    as counted_on,
    {{ j_num('quantity_on_hand') }}                                 as quantity_on_hand,
    {{ j_num('unit_cost') }}                                        as unit_cost,
    {{ j_str('source_file') }}                                      as source_file,
    _source_updated_at                                              as exported_at
from latest
