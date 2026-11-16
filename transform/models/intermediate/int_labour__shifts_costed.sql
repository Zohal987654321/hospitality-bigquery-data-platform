-- Shifts on the same venue key and trading date as sales, with paid hours.

with shifts as (
    select * from {{ ref('stg_workforce__shifts') }}
),

locations as (
    select * from {{ ref('location_crosswalk') }}
)

select
    s.shift_id,
    s.employee_key,
    coalesce(loc.location_key, 'UNMAPPED')                                as location_key,
    s.role,
    s.shift_status,
    s.start_at_utc,
    s.end_at_utc,
    datetime(s.start_at_utc, loc.timezone)                                as start_at_local,
    {{ business_date('s.start_at_utc', 'loc.timezone') }}                 as business_date,
    s.break_minutes,
    round(
        (timestamp_diff(s.end_at_utc, s.start_at_utc, minute) - coalesce(s.break_minutes, 0))
        / 60, 2
    )                                                                     as paid_hours,
    s.labour_cost,
    s.source_updated_at
from shifts s
left join locations loc
    on loc.workforce_location_id = s.workforce_location_id
