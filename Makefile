.PHONY: install dev test lint validate-skills doctor secret-scan check clean eval eval-skill eval-preview eval-init

PYTHON ?= python3

install:
	pip install .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/ scripts/ .agents/skills/

validate-skills:
	$(PYTHON) scripts/skill_validate.py validate

doctor:
	$(PYTHON) scripts/doctor.py check

secret-scan:
	$(PYTHON) scripts/secret_scan.py .

check: lint validate-skills test

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

# --- Skillgrade evals ---

EVAL_DIRS := $(wildcard evals/*/eval.yaml)
EVAL_SKILLS := $(patsubst evals/%/eval.yaml,%,$(EVAL_DIRS))
SKILL ?=
EVAL_PATH := $(CURDIR)/evals/bin:$(PATH)
RESULTS_DIR ?= results

eval:
	@mkdir -p $(RESULTS_DIR)
	@for skill in $(filter-out _template,$(EVAL_SKILLS)); do \
		echo "=== eval: $$skill ==="; \
		cd evals/$$skill && \
		if [ -f "$(CURDIR)/.env" ]; then set -a; . "$(CURDIR)/.env"; set +a; fi && \
		mkdir -p "$(CURDIR)/.cache" && \
		export PATH="$(EVAL_PATH)" && \
		export XDG_CACHE_HOME="$(CURDIR)/.cache" && \
		export NIM_API_KEY="$${NIM_API_KEY:-$${INFERENCE_API_KEY:-}}" && \
		export NIM_BASE_URL="$${NIM_BASE_URL:-$${GATEWAY_URL:-}}" && \
		export NIM_MODEL="$${NIM_MODEL:-azure/openai/gpt-4.1-mini}" && \
		skillgrade --smoke --provider=local --output="$(CURDIR)/$(RESULTS_DIR)" && \
		cd ../..; \
	done
	@$(PYTHON) evals/bin/summarize.py $(RESULTS_DIR)/

eval-skill:
ifndef SKILL
	$(error SKILL is required. Usage: make eval-skill SKILL=nuwa)
endif
	@mkdir -p $(RESULTS_DIR)
	cd evals/$(SKILL) && \
	if [ -f "$(CURDIR)/.env" ]; then set -a; . "$(CURDIR)/.env"; set +a; fi && \
	mkdir -p "$(CURDIR)/.cache" && \
	export PATH="$(EVAL_PATH)" && \
	export XDG_CACHE_HOME="$(CURDIR)/.cache" && \
	export NIM_API_KEY="$${NIM_API_KEY:-$${INFERENCE_API_KEY:-}}" && \
	export NIM_BASE_URL="$${NIM_BASE_URL:-$${GATEWAY_URL:-}}" && \
	export NIM_MODEL="$${NIM_MODEL:-azure/openai/gpt-4.1-mini}" && \
	skillgrade --smoke --provider=local --output="$(CURDIR)/$(RESULTS_DIR)"
	@$(PYTHON) evals/bin/summarize.py $(RESULTS_DIR)/

eval-preview:
	skillgrade preview

eval-init:
ifndef SKILL
	$(error SKILL is required. Usage: make eval-init SKILL=newskill)
endif
	@if [ -d "evals/$(SKILL)" ]; then echo "evals/$(SKILL) already exists"; exit 1; fi
	cp -r evals/_template evals/$(SKILL)
	@sed -i 's/SKILL_NAME/$(SKILL)/g' evals/$(SKILL)/eval.yaml
	@mkdir -p evals/$(SKILL)/fixtures evals/$(SKILL)/graders
	@echo "Scaffolded evals/$(SKILL)/. Next steps:"
	@echo "  1. Edit evals/$(SKILL)/eval.yaml — design tasks that test $(SKILL)'s core claim"
	@echo "  2. Add fixture files to evals/$(SKILL)/fixtures/"
	@echo "  3. Write graders in evals/$(SKILL)/graders/"
	@echo "  4. Run: make eval-skill SKILL=$(SKILL)"

# --- Skill improvement pipeline ---

improve:
	$(PYTHON) evals/bin/improve.py $(RESULTS_DIR)/ --skills-dir .agents/skills/ --output $(RESULTS_DIR)/improvements/

improve-propose:
	$(PYTHON) evals/bin/improve.py $(RESULTS_DIR)/ --skills-dir .agents/skills/ --propose --output $(RESULTS_DIR)/improvements/

improve-apply:
	$(PYTHON) evals/bin/improve.py $(RESULTS_DIR)/ --skills-dir .agents/skills/ --apply --output $(RESULTS_DIR)/improvements/
