-- Pseudonymised employee dimension: role and contract attributes only.
select
    e.employee_key,
    e.manager_employee_key,
    e.role,
    e.employment_type,
    e.employment_status,
    loc.location_key                                        as home_location_key,
    e.start_date,
    date_diff(current_date('Australia/Sydney'), e.start_date, month) as tenure_months
from {{ ref('stg_workforce__employees') }} e
left join {{ ref('location_crosswalk') }} loc
    on loc.workforce_location_id = e.home_workforce_location_id
