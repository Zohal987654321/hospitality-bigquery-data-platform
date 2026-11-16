{%- set fy_start = var('fiscal_year_start_month') -%}

with days as (
    select date_day
    from unnest(generate_date_array(
        date('{{ var("date_spine_start") }}'), date('{{ var("date_spine_end") }}')
    )) as date_day
)

select
    cast(format_date('%Y%m%d', date_day) as int64)                         as date_key,
    date_day,
    format_date('%A', date_day)                                            as day_name,
    extract(dayofweek from date_day) in (1, 7)                             as is_weekend,
    date_trunc(date_day, isoweek)                                          as week_start_date,
    extract(isoweek from date_day)                                         as iso_week,
    date_trunc(date_day, month)                                            as month_start_date,
    format_date('%b %Y', date_day)                                         as month_label,
    extract(day from last_day(date_day, month))                            as days_in_month,
    extract(year from date_day)                                            as calendar_year,
    extract(year from date_add(date_day, interval {{ 13 - fy_start }} month)) as fiscal_year,
    mod(extract(month from date_day) - {{ fy_start }} + 12, 12) + 1        as fiscal_month_number,
    div(mod(extract(month from date_day) - {{ fy_start }} + 12, 12), 3) + 1 as fiscal_quarter
from days
