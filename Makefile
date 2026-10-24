PYTHON ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)
export PYTHONPATH := .

.PHONY: validate test replay-stubs demo-stub demo-correction-loop demo-graduation eval-learning sim-eval extract-eval latte-bench serve ingest ingest-refresh data-report sources-refresh sources-status \
	export-training export-laya laya-train sync push modal-secrets modal-deploy-s1 modal-deploy-s2 modal-deploy-sapling modal-deploy-stt modal-finetune docker-build docker-run

IMAGE ?= baansafe-api:local
DATASET ?= eval/out/sft.jsonl
TRAINING_OUT ?= training/out

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

demo-graduation:
	$(PYTHON) -m eval.graduation_demo

eval-learning:
	$(PYTHON) -m eval.learning

sim-eval:
	$(PYTHON) -m sim

# EXTRACT_EVAL_SET=fixtures (default, the original 24) | synthetic | all
extract-eval:
	$(PYTHON) -m eval.extract_eval

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

# Live public sources for the demo provinces. Writes data/snapshots/.
sources-refresh:
	$(PYTHON) -m ingest.demo_sources --refresh

# Offline status from the committed snapshots. Sends no request.
sources-status:
	$(PYTHON) -m ingest.demo_sources

# Event-log export. SYNTHETIC=1 also writes SetFit rows from fixtures/synthetic.
export-training:
	$(PYTHON) -m training.export --out "$(TRAINING_OUT)"
	@if [ "$(SYNTHETIC)" = "1" ]; then $(PYTHON) -m training.synthetic_export --out "$(TRAINING_OUT)"; fi

# Laya JSONL: state.body, one NIEMS colour choice, noul for the other labels.
# laya-train --data training/out/laya/train.jsonl --eval training/out/laya/held.jsonl \
#   --base convaiinnovations/laya-multilingual --out training/out/laya-ckpt
export-laya:
	$(PYTHON) -m training.laya_export --out "$(TRAINING_OUT)/laya"

# Fine-tune only when LAYA_TRAIN=1 and a GPU or Modal task is present. Otherwise skips.
laya-train:
	$(PYTHON) scripts/laya_train.py

# Teammate sync (download): git pull, .env, .venv + pip, Modal check, secrets.
sync:
	$(PYTHON) scripts/sync_workspace.py

# Opposite of sync (send): Modal secrets + git push main. Optional MSG='...' commits first.
push:
	$(PYTHON) scripts/push_workspace.py

# Push HF_TOKEN / MUBIT_API_KEY from gitignored .env into Modal secrets. Values are not printed.
modal-secrets:
	$(PYTHON) scripts/sync_modal_secrets.py

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
