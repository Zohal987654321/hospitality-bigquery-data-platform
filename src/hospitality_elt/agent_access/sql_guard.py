"""Defence-in-depth checks for SQL written by AI agents.

The real boundary is IAM: the agent's service account can only read the ``ai``
dataset (authorised views) and run jobs with a byte cap. These checks give the
agent fast, readable errors and stop obvious misuse before a job is submitted.
"""

from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|create|drop|alter|truncate|grant|revoke|call|execute"
    r"|export|load|declare|begin|commit|rollback)\b",
    re.IGNORECASE,
)
TABLE_REF = re.compile(
    r"\b(?:from|join)\s+`?([a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+){1,2})`?", re.IGNORECASE
)


class UnsafeQueryError(ValueError):
    pass


def _strip_comments_and_strings(sql: str) -> str:
    sql = re.sub(r"--[^\n]*|#[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "''", sql)
    return sql


def check_query(sql: str, allowed_datasets: set[str]) -> str:
    """Return the cleaned query, or raise ``UnsafeQueryError`` with the reason."""
    stripped = sql.strip().rstrip(";").strip()
    body = _strip_comments_and_strings(stripped)
    if ";" in body:
        raise UnsafeQueryError("Only a single statement is allowed.")
    if not re.match(r"^\s*(select|with)\b", body, re.IGNORECASE):
        raise UnsafeQueryError("Only SELECT queries are allowed.")
    if FORBIDDEN.search(body):
        raise UnsafeQueryError("Query contains a statement keyword that is not allowed.")
    if re.search(r"information_schema", body, re.IGNORECASE):
        raise UnsafeQueryError("Use the describe_table tool for metadata.")

    refs = TABLE_REF.findall(body)
    cte_names = {m.lower() for m in re.findall(r"\b(\w+)\s+as\s*\(", body, re.IGNORECASE)}
    for ref in refs:
        parts = ref.split(".")
        if len(parts) == 1 and parts[0].lower() in cte_names:
            continue
        dataset = parts[-2]
        if dataset not in allowed_datasets:
            raise UnsafeQueryError(
                f"Table {ref!r} is outside the allowed datasets: {sorted(allowed_datasets)}"
            )
    if not refs:
        raise UnsafeQueryError("Query must read from a table in the allowed datasets.")
    return stripped
