with latest as (
    {{ latest_version(source('raw_pos', 'locations')) }}
)

select
    {{ j_str('location_id') }}                as pos_location_id,
    {{ j_str('name') }}                       as pos_location_name,
    {{ j_str('timezone') }}                   as pos_timezone,
    _source_updated_at                        as source_updated_at
from latest
