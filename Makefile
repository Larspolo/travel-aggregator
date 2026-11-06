# Common tasks of travel-aggregator. The service name `app` is in docker-compose.yml.
# Usage: make up | down | logs | test | migrate | backup | restore FILE=<backup file>

.PHONY: up down logs test migrate backup restore

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f app

test:
	python3 -m pytest -n auto

migrate:
	docker compose exec app alembic upgrade head

backup:
	docker compose exec app python -m app.backup --now

restore:
	@if [ -z "$(FILE)" ]; then echo "FILE is empty. Usage: make restore FILE=<backup file>"; exit 1; fi
	docker compose exec app python -m app.restore $(FILE)
