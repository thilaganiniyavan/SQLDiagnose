# Common tasks. Uses the project virtual environment if it exists.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
NPM := npm --prefix frontend

.PHONY: help setup frontend model data train finetune evaluate api demo dev test test-api test-web e2e lint docker

help:
	@echo "make setup     install Python dependencies (.venv) and build the web app"
	@echo "make model     download the fine-tuned classifier (GitHub release)"
	@echo "make api       start the app: UI + REST API on http://localhost:8000"
	@echo "make demo      serve the app on a temporary public HTTPS link (Cloudflare quick tunnel)"
	@echo "make dev       web app with hot reload on http://localhost:5173 (run 'make api' too)"
	@echo "make frontend  (re)build the web app into frontend/dist"
	@echo "make test      Python tests + web app unit tests"
	@echo "make e2e       browser end-to-end tests (needs 'make frontend'; starts the API if needed)"
	@echo "make lint      typecheck and lint the web app"
	@echo "make docker    build and start the Docker image on :8000"
	@echo "make data      download Spider and rebuild the dataset (also enables running queries on the examples)"
	@echo "make train     train the classifier from scratch (hours on CPU)"
	@echo "make finetune  continue fine-tuning the released checkpoint"
	@echo "make evaluate  regenerate reports/ (needs Spider: make data)"

setup:
	[ -d .venv ] || python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt
	$(MAKE) frontend

frontend:
	$(NPM) ci
	$(NPM) run build

model:
	$(PY) scripts/download_model.py

data:
	$(PY) -m data_pipeline.build_dataset --download

train:
	$(PY) -m training.train

finetune:
	$(PY) -m training.train --init-from models/checkpoints/codeberta-small/best \
		--output-dir models/checkpoints/codeberta-small-ft --epochs 2 --lr 2e-5 --batch-size 8 --grad-accum 2

evaluate:
	$(PY) -m evaluation.evaluate --model-dir models/checkpoints/codeberta-small-ft/best

api:
	$(PY) -m uvicorn deployment.api.main:app --host 127.0.0.1 --port 8000

demo:
	bash scripts/demo_tunnel.sh

dev:
	$(NPM) run dev

test: test-api test-web

test-api:
	$(PY) -m pytest -q

test-web:
	$(NPM) test

e2e:
	cd frontend && npx playwright test

lint:
	$(NPM) run typecheck
	$(NPM) run lint

docker:
	docker compose -f deployment/docker-compose.yml up --build
