.PHONY: up migrate seed extract_sample eval_sample test run

# Run from repo root
ROOT := $(shell git rev-parse --show-toplevel 2>/dev/null || echo "..")
export PYTHONPATH := $(ROOT)/cloud-compliance-engine:$(ROOT)

up:
	docker-compose -f $(ROOT)/docker-compose.yml up -d 2>/dev/null || true

migrate:
	cd $(ROOT) && alembic upgrade head

seed:
	cd $(ROOT) && PYTHONPATH=cloud-compliance-engine python -m app.scripts.seed_catalog

extract_sample:
	@echo "Use POST /v1/evaluation-runs with s3_prefix pointing to a sample snapshot JSON path"

eval_sample:
	@echo "Use POST /v1/evaluation-runs with snapshot_id after extract"

test:
	cd $(ROOT) && PYTHONPATH=cloud-compliance-engine python -m pytest cloud-compliance-engine/tests -v

run:
	cd $(ROOT) && PYTHONPATH=cloud-compliance-engine python -m uvicorn app.main:app --reload --app-dir cloud-compliance-engine --host 0.0.0.0 --port 8000
