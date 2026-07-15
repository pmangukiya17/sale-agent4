.PHONY: up down logs build migrate revision backend-shell db-shell smoke-test

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

migrate:
	docker compose exec backend alembic upgrade head

revision:
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

backend-shell:
	docker compose exec backend bash

db-shell:
	docker compose exec db psql -U $${POSTGRES_USER:-sales_agent} -d $${POSTGRES_DB:-sales_agent}

# Mandatory gate before starting any milestone. Assumes the stack from
# `make up` is already running; does not start/stop containers itself.
smoke-test:
	python3 smoke_test.py
