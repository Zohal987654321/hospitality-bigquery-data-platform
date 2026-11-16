with transactions as (
    select
        {{ j_str('transaction_id') }} as transaction_id,
        payload,
        _source_updated_at
    from {{ ref('base_pos__transactions_latest') }}
)

select
    {{ surrogate_key(['t.transaction_id', "json_value(line, '$.line_id')"]) }}
                                                                  as transaction_line_key,
    t.transaction_id,
    json_value(line, '$.line_id')                                 as line_id,
    json_value(line, '$.product_id')                              as pos_product_id,
    upper(trim(json_value(line, '$.sku')))                        as sku,
    safe_cast(json_value(line, '$.quantity') as numeric)          as quantity,
    safe_cast(json_value(line, '$.unit_price') as numeric)        as unit_price,
    safe_cast(json_value(line, '$.discount') as numeric)          as discount_amount,
    safe_cast(json_value(line, '$.tax') as numeric)               as tax_amount,
    safe_cast(json_value(line, '$.net_amount') as numeric)        as net_amount,
    t._source_updated_at                                          as source_updated_at
from transactions t
cross join unnest(json_query_array(t.payload, '$.line_items')) as line
