{{ config(materialized='ephemeral') }}

-- Latest version of every transaction; shared by the header and line models.
{{ latest_version(source('raw_pos', 'transactions')) }}
