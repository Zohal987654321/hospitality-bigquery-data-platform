{{
    config(
        partition_by={'field': 'business_date', 'data_type': 'date', 'granularity': 'day'},
        cluster_by=['location_key']
    )
}}

-- Grain: one row per venue per trading day. Every venue gets a row for every day in
-- the data range, so "zero sales" is visible instead of silently missing.

with sales as (
    select
        location_key,
        business_date,
        sum(if(transaction_status in ('completed', 'refund'), net_amount, 0))        as net_sales,
        sum(if(transaction_status = 'refund', net_amount, 0))                        as refunds,
        sum(if(transaction_status = 'completed', discount_amount, 0))                as discounts,
        count(distinct if(transaction_status = 'completed', transaction_id, null))   as transaction_count,
        sum(if(transaction_status = 'completed', quantity, 0))                       as items_sold,
        sum(if(transaction_status in ('completed', 'refund'), estimated_cost_of_goods, 0))
                                                                                     as estimated_cogs
    from {{ ref('fct_sales_lines') }}
    group by 1, 2
),

labour as (
    select
        location_key,
        business_date,
        sum(paid_hours)                 as labour_hours,
        sum(labour_cost)                as labour_cost,
        count(distinct employee_key)    as staff_rostered
    from {{ ref('fct_labour_shifts') }}
    group by 1, 2
),

bounds as (
    select min(business_date) as first_day, max(business_date) as last_day
    from (select business_date from sales union all select business_date from labour)
),

spine as (
    select l.location_key, l.location_name, d.date_key, d.date_day as business_date,
           d.days_in_month, d.month_start_date
    from {{ ref('dim_location') }} l
    cross join {{ ref('dim_date') }} d
    cross join bounds b
    where d.date_day between b.first_day and b.last_day
),

budget as (
    select location_key, budget_month, budget_net_sales
    from {{ ref('location_monthly_budget') }}
)

select
    s.location_key,
    s.location_name,
    s.date_key,
    s.business_date,
    coalesce(sa.net_sales, 0)                                         as net_sales,
    coalesce(sa.refunds, 0)                                           as refunds,
    coalesce(sa.discounts, 0)                                         as discounts,
    coalesce(sa.transaction_count, 0)                                 as transaction_count,
    coalesce(sa.items_sold, 0)                                        as items_sold,
    round(safe_divide(sa.net_sales, sa.transaction_count), 2)         as avg_transaction_value,
    coalesce(sa.estimated_cogs, 0)                                    as estimated_cogs,
    round(safe_divide(sa.estimated_cogs, sa.net_sales), 4)            as estimated_cogs_pct,
    coalesce(lb.labour_hours, 0)                                      as labour_hours,
    coalesce(lb.labour_cost, 0)                                       as labour_cost,
    coalesce(lb.staff_rostered, 0)                                    as staff_rostered,
    round(safe_divide(lb.labour_cost, sa.net_sales), 4)               as labour_cost_pct,
    round(safe_divide(sa.net_sales, lb.labour_hours), 2)              as sales_per_labour_hour,
    round(safe_divide(bu.budget_net_sales, s.days_in_month), 2)       as budget_net_sales,
    round(coalesce(sa.net_sales, 0)
          - safe_divide(bu.budget_net_sales, s.days_in_month), 2)     as variance_to_budget,
    current_timestamp()                                               as built_at
from spine s
left join sales sa
    on sa.location_key = s.location_key and sa.business_date = s.business_date
left join labour lb
    on lb.location_key = s.location_key and lb.business_date = s.business_date
left join budget bu
    on bu.location_key = s.location_key and bu.budget_month = s.month_start_date
