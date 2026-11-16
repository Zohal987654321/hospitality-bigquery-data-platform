{{
    config(
        partition_by={'field': 'business_date', 'data_type': 'date', 'granularity': 'day'},
        cluster_by=['location_key']
    )
}}

-- Grain: one row per rostered/worked shift. Rejected shifts are excluded.
select
    shift_id,
    employee_key,
    location_key,
    cast(format_date('%Y%m%d', business_date) as int64) as date_key,
    business_date,
    role,
    shift_status,
    start_at_local,
    break_minutes,
    paid_hours,
    labour_cost
from {{ ref('int_labour__shifts_costed') }}
where shift_status != 'rejected'
