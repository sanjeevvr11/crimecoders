# Trace360: run the whole app locally (macOS / Linux).
#   make setup      create backend/.venv, install Python + npm dependencies
#   make pipeline   ingest data/raw, train models, score, write the evaluation report
#   make dev        start API (:8000) and web app (:5173) together; Ctrl-C stops both
#                   (first run creates the demo users listed in the README)
# Other targets: api, web, test, typecheck, build, contract, examples, clean

PY      ?= $(shell command -v python3.11 || command -v python3.12 || command -v python3.13 || command -v python3)
VENV    := backend/.venv
VPY     := $(VENV)/bin/python
API_PORT ?= 8000
WEB_PORT ?= 5173

.PHONY: setup pipeline api web dev test typecheck build contract examples check-data clean demo-users user

setup:
	@$(PY) -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"' || (echo "Install Python 3.11+ first"; exit 1)
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install --upgrade pip
	$(VPY) -m pip install -e "backend[dev]"
	cd frontend && npm install
	@echo "Setup done. Put the 25 N_SOA.xls/.xlsx files in data/raw/, then: make pipeline && make dev"

check-data:
	@ls data/raw/*_SOA.xls* >/dev/null 2>&1 || (echo "No statements in data/raw/. Copy the 25 N_SOA.xls/.xlsx files there (see README)."; exit 1)

pipeline: check-data
	cd backend && .venv/bin/python scripts/train.py

api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port $(API_PORT)

web:
	cd frontend && npm run dev -- --port $(WEB_PORT)

dev:
	@test -f data/auth.sqlite3 || (echo "No users yet: creating the three demo users"; $(MAKE) --no-print-directory demo-users)
	@echo "API  http://localhost:$(API_PORT)/docs"
	@echo "Web  http://localhost:$(WEB_PORT)"
	@trap 'kill 0' INT TERM EXIT; \
	  (cd backend && .venv/bin/uvicorn app.main:app --port $(API_PORT)) & \
	  (cd frontend && npm run dev -- --port $(WEB_PORT)) & \
	  wait

test:
	cd backend && .venv/bin/python -m pytest -q

typecheck:
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

# sign-in users (stored in data/auth.sqlite3): three demo users, or one user of your choice
#   make user USERNAME=priya ROLE=investigator
demo-users:
	cd backend && .venv/bin/python scripts/create_user.py --demo

user:
	cd backend && .venv/bin/python scripts/create_user.py --username $(USERNAME) --role $(ROLE)

# regenerate the API contract and the frontend types after changing backend response models
contract:
	cd backend && .venv/bin/python scripts/export_openapi.py
	cd frontend && npm run gen:api

examples:
	cd backend && .venv/bin/python scripts/export_api_examples.py

clean:
	rm -rf frontend/dist data/processed/*.parquet data/processed/stats.json data/trace360.duckdb
