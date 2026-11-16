-- A new venue in the POS without a crosswalk row would silently drop out of reporting.
-- Fail loudly instead, so someone adds it to seeds/location_crosswalk.csv.
select distinct t.pos_location_id
from {{ ref('stg_pos__transactions') }} t
left join {{ ref('location_crosswalk') }} c using (pos_location_id)
where c.location_key is null

union all

select distinct s.workforce_location_id
from {{ ref('stg_workforce__shifts') }} s
left join {{ ref('location_crosswalk') }} c using (workforce_location_id)
where c.location_key is null
