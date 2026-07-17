.PHONY: up down logs build migrate revision backend-shell db-shell smoke-test frontend-deps-reset

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

# The frontend service bind-mounts the host source (./frontend:/app) for
# hot-reload, with `/app/node_modules` as an anonymous volume so the
# container's own npm-installed packages aren't shadowed by whatever (or
# nothing) is on the host. That anonymous volume is created once and then
# PERSISTS across every later `docker compose up --build`, even though the
# image's own npm install layer correctly reruns whenever package.json
# changes. Net effect: after adding/removing a frontend dependency, `docker
# compose build` succeeds but the running container still has the old
# node_modules, and Vite fails with "Failed to resolve import ...". Run
# this target (or `docker compose up --build -V frontend`) any time
# frontend/package.json changes.
frontend-deps-reset:
	docker compose up --build --renew-anon-volumes frontend

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
