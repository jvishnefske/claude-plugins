.PHONY: test coverage clean lint

test:
	pytest

coverage:
	pytest --cov=swiss-cheese --cov-report=json --cov-report=html:coverage

lint:
	ruff check .

clean:
	rm -rf .coverage htmlcov coverage .pytest_cache
