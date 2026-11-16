select
    {{ j_str('transaction_id') }}             as transaction_id,
    {{ j_str('location_id') }}                as pos_location_id,
    {{ j_str('register_id') }}                as register_id,
    {{ j_str('staff_id') }}                   as staff_key,  -- pseudonymised at ingestion
    lower({{ j_str('status') }})              as transaction_status,
    lower({{ j_str('channel') }})             as sales_channel,
    {{ j_ts('opened_at') }}                   as opened_at_utc,
    {{ j_ts('closed_at') }}                   as closed_at_utc,
    {{ j_num('total_net') }}                  as total_net,
    {{ j_num('total_tax') }}                  as total_tax,
    _source_updated_at                        as source_updated_at,
    _ingested_at,
    _run_id
from {{ ref('base_pos__transactions_latest') }}
