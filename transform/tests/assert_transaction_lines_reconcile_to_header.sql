-- Every transaction's line net amounts must add up to its header total (±1 cent).
-- Ingestion already rejects these; this catches anything that slips through later.
select
    t.transaction_id,
    t.total_net,
    sum(l.net_amount) as lines_net
from {{ ref('stg_pos__transactions') }} t
join {{ ref('stg_pos__transaction_lines') }} l using (transaction_id)
group by 1, 2
having abs(t.total_net - sum(l.net_amount)) > 0.01
