.PHONY: backend-test frontend-test

backend-test:
	pytest backend/tests

frontend-test:
	cd frontend && npm test

