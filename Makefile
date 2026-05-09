PYTHON = .venv/bin/python
PIP    = .venv/bin/pip

.PHONY: install lint format test local-up local-down ui ingest build deploy

install:
	python3 -m venv .venv
	$(PIP) install --quiet opensearch-py boto3 requests pytest pytest-mock "moto[sqs]" fastembed streamlit python-dotenv "google-genai>=1.0.0"

lint:
	.venv/bin/ruff check .

format:
	.venv/bin/ruff format .

test:
	$(PYTHON) -m pytest tests/unit -v

local-up:
	docker-compose up -d

local-down:
	docker-compose down

ui:
	.venv/bin/streamlit run ui/app.py

ingest:
	set -a && . ./.env && $(PYTHON) script/ingest_files.py $(FILES)

build:
	sam build --cached --parallel

deploy: build
	sam deploy
