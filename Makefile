PYTHON ?= python3
export PYTHONPATH := .

.PHONY: validate test replay-stubs demo-stub demo-correction-loop serve ingest ingest-refresh data-report

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

serve:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

ingest:
	$(PYTHON) -m ingest

ingest-refresh:
	$(PYTHON) -m ingest --refresh

data-report:
	$(PYTHON) -m ingest.report
