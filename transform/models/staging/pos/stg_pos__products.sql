with latest as (
    {{ latest_version(source('raw_pos', 'products')) }}
)

select
    {{ j_str('product_id') }}                 as pos_product_id,
    upper(trim({{ j_str('sku') }}))           as sku,
    {{ j_str('name') }}                       as product_name,
    {{ j_str('category') }}                   as product_category,
    {{ j_num('price') }}                      as list_price,
    {{ j_num('unit_cost') }}                  as unit_cost,
    _source_updated_at                        as source_updated_at
from latest
