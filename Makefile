.PHONY: \
	backend-install backend-migrate backend-run backend-test frontend-test postgres-up \
	docker-build docker-config docker-up docker-down docker-logs docker-ps docker-migrate

.PHONY: user-create frontend-check
USERNAME ?= admin

VENV ?= .venv
DOCKER_CONTEXT ?= default
COMPOSE := docker --context $(DOCKER_CONTEXT) compose

backend-install:
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install -e 'backend[test]'

postgres-up:
	$(COMPOSE) up -d --wait postgres

backend-migrate:
	$(VENV)/bin/alembic -c backend/alembic.ini upgrade head

backend-run:
	$(VENV)/bin/uvicorn app.main:app --reload --app-dir backend

backend-test:
	$(VENV)/bin/pytest backend/tests

frontend-test:
	cd frontend && npm test

docker-config:
	$(COMPOSE) config --quiet

docker-build: docker-config
	$(COMPOSE) build

docker-up: docker-config
	$(COMPOSE) up --build -d --wait

docker-down:
	$(COMPOSE) down

docker-logs:
	$(COMPOSE) logs -f --tail=200

docker-ps:
	$(COMPOSE) ps

docker-migrate:
	$(COMPOSE) run --rm migrate

user-create:
	$(COMPOSE) exec api python -m app.admin create-user --username $(USERNAME) --role admin --site '*'

frontend-check:
	cd frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build
