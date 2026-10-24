PYTHON ?= python3
export PYTHONPATH := .

.PHONY: validate test replay-stubs demo-stub demo-correction-loop eval-learning latte-bench serve ingest ingest-refresh data-report \
	modal-deploy-s1 modal-deploy-s2 modal-deploy-sapling modal-deploy-stt modal-finetune docker-build docker-run

IMAGE ?= baansafe-api:local
DATASET ?= eval/out/sft.jsonl

validate:
	$(PYTHON) scripts/validate.py

test:
	$(PYTHON) -m pytest -q

replay-stubs:
	$(PYTHON) -m eval

demo-stub:
	$(PYTHON) -m gateway

demo-correction-loop:
	$(PYTHON) -m eval.correction_loop

eval-learning:
	$(PYTHON) -m eval.learning

# Free mode replays the calibrated reference and exits. No API call.
# LATTE_SERVE=1 starts `bun run dev` in the submodule (Try without an API).
# LATTE_LIVE=1 is that UI with Mubit gateway env required. Keys are not printed.
latte-bench:
	$(PYTHON) -m eval.latte

serve:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

ingest:
	$(PYTHON) -m ingest

ingest-refresh:
	$(PYTHON) -m ingest --refresh

data-report:
	$(PYTHON) -m ingest.report

modal-deploy-s1:
	$(PYTHON) -m modal deploy -m infra.modal.s1_app

modal-deploy-s2:
	$(PYTHON) -m modal deploy -m infra.modal.s2_app

modal-deploy-sapling:
	$(PYTHON) -m modal deploy -m infra.modal.sapling_app

modal-deploy-stt:
	$(PYTHON) -m modal deploy -m infra.modal.stt_app

modal-finetune:
	$(PYTHON) -m modal run -m infra.modal.finetune_app --dataset "$(DATASET)"

docker-build:
	docker build -f docker/Dockerfile -t $(IMAGE) .

docker-run:
	docker run --rm -p 8000:8000 $(IMAGE)
