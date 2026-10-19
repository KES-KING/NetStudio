# Local development helpers only. Manage containers with docker compose directly.
.PHONY: backend-install backend-migrate backend-run backend-test frontend-test frontend-check

VENV ?= .venv

backend-install:
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install -e 'backend[test]'

backend-migrate:
	$(VENV)/bin/alembic -c backend/alembic.ini upgrade head

backend-run:
	$(VENV)/bin/uvicorn app.main:app --reload --app-dir backend

backend-test:
	$(VENV)/bin/pytest backend/tests

frontend-test:
	cd frontend && npm test

frontend-check:
	cd frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build
