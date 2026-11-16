select
    c.location_key,
    c.location_name,
    c.state,
    c.timezone,
    c.opened_on,
    c.pos_location_id,
    c.workforce_location_id,
    c.inventory_location_code,
    p.pos_location_name   -- name as held in the POS, for spotting drift
from {{ ref('location_crosswalk') }} c
left join {{ ref('stg_pos__locations') }} p
    on p.pos_location_id = c.pos_location_id
