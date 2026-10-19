.PHONY: backend-install backend-migrate backend-run backend-test frontend-test postgres-up

VENV ?= .venv
DOCKER_CONTEXT ?= default

backend-install:
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install -e 'backend[test]'

postgres-up:
	docker --context $(DOCKER_CONTEXT) compose up -d --wait postgres

backend-migrate:
	$(VENV)/bin/alembic -c backend/alembic.ini upgrade head

backend-run:
	$(VENV)/bin/uvicorn app.main:app --reload --app-dir backend

backend-test:
	$(VENV)/bin/pytest backend/tests

frontend-test:
	cd frontend && npm test
