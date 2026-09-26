# Common tasks. Uses the project virtual environment if it exists.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: help setup model data train finetune evaluate api ui test demo

help:
	@echo "make setup     install dependencies into .venv"
	@echo "make model     download the fine-tuned classifier (GitHub release)"
	@echo "make api       start the REST API on :8000"
	@echo "make ui        start the Streamlit UI on :8501"
	@echo "make test      run the test suite"
	@echo "make data      rebuild the dataset from Spider (downloads ~200 MB)"
	@echo "make train     train the classifier from scratch (hours on CPU)"
	@echo "make finetune  continue fine-tuning the released checkpoint"
	@echo "make evaluate  regenerate reports/ (needs Spider: make data)"

setup:
	[ -d .venv ] || python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

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
	$(PY) -m uvicorn deployment.api.main:app --port 8000

ui:
	$(PY) -m streamlit run frontend/app.py

test:
	$(PY) -m pytest -q
