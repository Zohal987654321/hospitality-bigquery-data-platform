.PHONY: install lint test dbt-parse mock-api demo clean

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

test:
	pytest -q

dbt-parse:
	cd transform && GCP_PROJECT_ID=ci-project dbt parse --profiles-dir .

# Generates the synthetic dataset + SFTP drop folder and serves the mock APIs on :8080
mock-api:
	python -m mock_sources.generator
	uvicorn mock_sources.app:app --port 8080

# Runs the full ingestion against the mock APIs and writes to ./.local
# (start `make mock-api` in another terminal first)
demo:
	set -a && . ./.env.example && set +a && \
	python -m hospitality_elt ingest --source all && \
	echo "\nSecond run (incremental, only the lookback window):" && \
	python -m hospitality_elt ingest --source pos --entity transactions

clean:
	rm -rf .local transform/target transform/logs mock_sources/sftp_drop
