PYTHON := .venv/bin/python
PIP := .venv/bin/pip
BLACK := .venv/bin/black
ISORT := .venv/bin/isort
FLAKE8 := .venv/bin/flake8
MYPY := .venv/bin/mypy

.PHONY: requirements start stop test black isort format flake8 mypy lint

requirements:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

start:
	docker compose up --build -d

stop:
	docker compose down

test:
	$(PYTHON) -m unittest discover -s src/tests

black:
	cd src && ../$(BLACK) --config pyproject.toml .

isort:
	cd src && ../$(ISORT) --settings-path setup.cfg .

format: isort black

flake8:
	cd src && ../$(FLAKE8) --config setup.cfg .

mypy:
	cd src && ../$(MYPY) --config-file setup.cfg .

lint: mypy flake8
