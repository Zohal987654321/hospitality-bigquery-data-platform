import pytest

from hospitality_elt.agent_access.sql_guard import UnsafeQueryError, check_query

ALLOWED = {"ai"}


@pytest.mark.parametrize(
    "sql",
    [
        "select * from ai.daily_location_performance limit 10",
        "SELECT location_name FROM `proj.ai.daily_location_performance` WHERE net_sales > 0;",
        """with w as (select * from ai.daily_location_performance)
       select location_name, avg(net_sales) from w group by 1""",
        "select * from ai.product_sales_daily where product_name = 'drop table x'",
    ],
)
def test_allows_read_only_queries_on_ai_dataset(sql):
    assert check_query(sql, ALLOWED)


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("delete from ai.daily_location_performance where true", "SELECT"),
        ("select 1; drop table ai.x", "single statement"),
        ("select * from marts.fct_sales_lines", "outside the allowed"),
        ("select * from `proj.raw_workforce.employees`", "outside the allowed"),
        (
            "select * from ai.t join staging.stg_workforce__employees e on true",
            "outside the allowed",
        ),
        ("select * from ai.INFORMATION_SCHEMA.TABLES", "describe_table"),
        ("select 1", "must read from a table"),
        ("with x as (select 1) insert into ai.t select * from x", "not allowed"),
    ],
)
def test_blocks_unsafe_queries(sql, reason):
    with pytest.raises(UnsafeQueryError, match=reason):
        check_query(sql, ALLOWED)
