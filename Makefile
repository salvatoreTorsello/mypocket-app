.PHONY: test test-unit test-integration test-bot test-cov \
        run-bot run-web run-all \
        migrate migrate-create reset-db \
        lint format \
        docker-build docker-up docker-down

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-bot:
	pytest tests/bot/ -v

test-cov:
	pytest --cov=app --cov-report=html --cov-report=term-missing
	@echo "Coverage report: open htmlcov/index.html"

# ── Running locally ───────────────────────────────────────────────────────────
run-bot:
	python -m app.bot.main

run-web:
	uvicorn app.main:app --reload --port 8000

run-all:
	make run-web & make run-bot

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

reset-db:
	rm -f mypocket.db
	alembic upgrade head
	python scripts/seed_categories.py
	@echo "Database reset and seeded."

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	ruff check app/ tests/
	mypy app/

format:
	ruff format app/ tests/

# ── Docker (local testing) ────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down
