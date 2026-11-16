with latest as (
    {{ latest_version(source('raw_workforce', 'shifts')) }}
)

select
    {{ j_str('shift_id') }}                                   as shift_id,
    {{ j_str('employee_id') }}                                as employee_key,
    {{ j_str('location_id') }}                                as workforce_location_id,
    lower({{ j_str('role') }})                                as role,
    lower({{ j_str('status') }})                              as shift_status,
    {{ j_ts('start_at') }}                                    as start_at_utc,
    {{ j_ts('end_at') }}                                      as end_at_utc,
    safe_cast({{ j_str('break_minutes') }} as int64)          as break_minutes,
    {{ j_num('labour_cost') }}                                as labour_cost,
    _source_updated_at                                        as source_updated_at
from latest
