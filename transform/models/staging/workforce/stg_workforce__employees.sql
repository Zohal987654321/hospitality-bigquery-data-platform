with latest as (
    {{ latest_version(source('raw_workforce', 'employees')) }}
)

select
    {{ j_str('employee_id') }}                as employee_key,  -- HMAC pseudonym
    {{ j_str('manager_id') }}                 as manager_employee_key,
    lower({{ j_str('role') }})                as role,
    lower({{ j_str('employment_type') }})     as employment_type,
    {{ j_str('home_location_id') }}           as home_workforce_location_id,
    lower({{ j_str('status') }})              as employment_status,
    safe_cast({{ j_str('start_date') }} as date) as start_date,
    _source_updated_at                        as source_updated_at
from latest
