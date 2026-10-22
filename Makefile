.PHONY: setup lint typecheck test test-private science run-api run-web demo docs synthetic audit

setup:
	uv sync --all-extras
	cd frontend && npm ci

lint:
	uv run ruff check src backend tests scripts
	uv run ruff format --check src backend tests scripts

typecheck:
	uv run mypy

test:
	uv run pytest -m "not private and not science" --cov=gravanom --cov-report=term

science:
	uv run pytest -m science

test-private:
	uv run pytest -m private

synthetic:
	uv run python scripts/make_synthetic.py

audit:
	uv run python scripts/audit_reproduction.py   # local only: needs the private data and script

run-api:
	uv run uvicorn app.main:app --app-dir backend --port 8000

run-web:
	cd frontend && npm run dev

demo:
	uv run gravanom export-static-demo --out frontend/public/demo
	cd frontend && npm run build:static

docs:
	uv run mkdocs build --strict
