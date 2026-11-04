# Lesson-8 convenience targets (run on the host with Docker Desktop up).
# The full seven-item self-check lives in reports/security-precheck.md;
# this target executes the two scriptable ones (SEC-05 / SEC-06).

.PHONY: check-security

check-security:
	docker compose exec -T api python scripts/check_security.py
