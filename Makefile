# AML Pipeline - Service Runner
# Usage:
#   make run       - Start all services (Redis, API, Celery, Streamlit)
#   make stop      - Stop all services
#   make status    - Check which services are running
#   make redis     - Start Redis only
#   make api       - Start API only
#   make celery    - Start Celery worker only
#   make ui        - Start Streamlit UI only
#   make logs      - Tail all service logs
#   make clean     - Stop all and remove log files

SHELL := /bin/bash

# Conda environment
CONDA_ENV := amlgan
CONDA_RUN := conda run --no-capture-output -n $(CONDA_ENV)

# Directories
PROJECT_DIR := $(shell pwd)
LOG_DIR := $(PROJECT_DIR)/.logs

# PID files
REDIS_PID := $(LOG_DIR)/redis.pid
API_PID := $(LOG_DIR)/api.pid
CELERY_PID := $(LOG_DIR)/celery.pid
UI_PID := $(LOG_DIR)/ui.pid

# Log files
REDIS_LOG := $(LOG_DIR)/redis.log
API_LOG := $(LOG_DIR)/api.log
CELERY_LOG := $(LOG_DIR)/celery.log
UI_LOG := $(LOG_DIR)/ui.log

# Ports
API_PORT := 8000
UI_PORT := 8501

# Colors
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[0;33m
CYAN := \033[0;36m
NC := \033[0m

.PHONY: run stop status redis api celery ui logs clean check-env kill-orphans help

help: ## Show this help
	@echo ""
	@echo "  AML Pipeline Runner"
	@echo "  ==================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-12s$(NC) %s\n", $$1, $$2}'
	@echo ""

$(LOG_DIR):
	@mkdir -p $(LOG_DIR)

# -------------------------------------------------------------------
# Prerequisites check
# -------------------------------------------------------------------
check-env: ## Check that all prerequisites are available
	@echo ""
	@echo "  Checking prerequisites..."
	@echo "  -------------------------"
	@printf "  %-20s" "conda env ($(CONDA_ENV)):" ; \
		conda env list 2>/dev/null | grep -q "$(CONDA_ENV)" \
		&& echo -e "$(GREEN)OK$(NC)" \
		|| { echo -e "$(RED)NOT FOUND$(NC)"; exit 1; }
	@printf "  %-20s" "redis-server:" ; \
		which redis-server >/dev/null 2>&1 \
		&& echo -e "$(GREEN)OK$(NC)" \
		|| { echo -e "$(RED)NOT FOUND$(NC)"; exit 1; }
	@printf "  %-20s" "uvicorn:" ; \
		$(CONDA_RUN) which uvicorn >/dev/null 2>&1 \
		&& echo -e "$(GREEN)OK$(NC)" \
		|| { echo -e "$(RED)NOT FOUND$(NC)"; exit 1; }
	@printf "  %-20s" "celery:" ; \
		$(CONDA_RUN) which celery >/dev/null 2>&1 \
		&& echo -e "$(GREEN)OK$(NC)" \
		|| { echo -e "$(RED)NOT FOUND$(NC)"; exit 1; }
	@printf "  %-20s" "streamlit:" ; \
		$(CONDA_RUN) which streamlit >/dev/null 2>&1 \
		&& echo -e "$(GREEN)OK$(NC)" \
		|| { echo -e "$(RED)NOT FOUND$(NC)"; exit 1; }
	@echo -e "  -------------------------"
	@echo -e "  $(GREEN)All prerequisites OK$(NC)"
	@echo ""

# -------------------------------------------------------------------
# Kill orphan processes from previous runs
# -------------------------------------------------------------------
kill-orphans: $(LOG_DIR) ## Kill orphan services and clean stale PID files
	@echo "  Cleaning up orphan processes..."
	@# Kill orphan processes on API port
	@fuser -k $(API_PORT)/tcp 2>/dev/null && echo -e "    Killed orphan on port $(API_PORT)" || true
	@# Kill orphan processes on UI port
	@fuser -k $(UI_PORT)/tcp 2>/dev/null && echo -e "    Killed orphan on port $(UI_PORT)" || true
	@# Kill orphan celery workers ([c] trick prevents pgrep matching itself)
	@pgrep -f '[c]elery.*app.workers' 2>/dev/null | xargs -r kill -9 2>/dev/null \
		&& echo -e "    Killed orphan Celery workers" || true
	@# Kill orphan conda wrappers for this project
	@pgrep -f '[c]onda run.*amlgan' 2>/dev/null | xargs -r kill -9 2>/dev/null \
		&& echo -e "    Killed orphan conda wrappers" || true
	@sleep 1
	@# Clean stale PID files
	@rm -f $(API_PID) $(CELERY_PID) $(UI_PID) $(REDIS_PID)
	@echo -e "  $(GREEN)Cleanup done$(NC)"

# -------------------------------------------------------------------
# Individual services
# -------------------------------------------------------------------
redis: $(LOG_DIR) ## Start Redis server
	@if redis-cli ping 2>/dev/null | grep -q PONG; then \
		echo -e "  $(YELLOW)Redis already running$(NC)"; \
	else \
		echo -n "  Starting Redis... "; \
		redis-server --daemonize yes --logfile $(REDIS_LOG) --port 6379; \
		sleep 1; \
		if redis-cli ping 2>/dev/null | grep -q PONG; then \
			redis-cli info server 2>/dev/null | grep process_id | cut -d: -f2 | tr -d '[:space:]' > $(REDIS_PID); \
			echo -e "$(GREEN)OK$(NC) (PID $$(cat $(REDIS_PID)))"; \
		else \
			echo -e "$(RED)FAILED$(NC) — check $(REDIS_LOG)"; \
			exit 1; \
		fi; \
	fi

api: $(LOG_DIR) redis ## Start FastAPI server (starts Redis first)
	@if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then \
		echo -e "  $(YELLOW)API already running$(NC) (PID $$(cat $(API_PID)))"; \
	else \
		echo -n "  Starting API server... "; \
		cd $(PROJECT_DIR) && \
		$(CONDA_RUN) uvicorn app.api.main:app --host 0.0.0.0 --port $(API_PORT) \
			> $(API_LOG) 2>&1 & \
		echo $$! > $(API_PID); \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			sleep 1; \
			if curl -s http://localhost:$(API_PORT)/status/health >/dev/null 2>&1; then \
				echo -e "$(GREEN)OK$(NC) (PID $$(cat $(API_PID)), port $(API_PORT))"; \
				break; \
			fi; \
			if [ $$i -eq 10 ]; then \
				echo -e "$(RED)FAILED$(NC) — check $(API_LOG)"; \
				exit 1; \
			fi; \
		done; \
	fi

celery: $(LOG_DIR) redis ## Start Celery worker (starts Redis first)
	@if [ -f $(CELERY_PID) ] && kill -0 $$(cat $(CELERY_PID)) 2>/dev/null; then \
		echo -e "  $(YELLOW)Celery already running$(NC) (PID $$(cat $(CELERY_PID)))"; \
	else \
		echo -n "  Starting Celery worker... "; \
		rm -f $(CELERY_PID); \
		cd $(PROJECT_DIR) && \
		$(CONDA_RUN) celery -A app.workers.celery_app worker -l info \
			> $(CELERY_LOG) 2>&1 & \
		echo $$! > $(CELERY_PID); \
		sleep 3; \
		if [ -f $(CELERY_PID) ] && kill -0 $$(cat $(CELERY_PID)) 2>/dev/null; then \
			echo -e "$(GREEN)OK$(NC) (PID $$(cat $(CELERY_PID)))"; \
		else \
			echo -e "$(RED)FAILED$(NC) — check $(CELERY_LOG)"; \
			exit 1; \
		fi; \
	fi

ui: $(LOG_DIR) api ## Start Streamlit UI (starts API + Redis first)
	@if [ -f $(UI_PID) ] && kill -0 $$(cat $(UI_PID)) 2>/dev/null; then \
		echo -e "  $(YELLOW)Streamlit already running$(NC) (PID $$(cat $(UI_PID)))"; \
	else \
		echo -n "  Starting Streamlit UI... "; \
		cd $(PROJECT_DIR) && \
		$(CONDA_RUN) streamlit run app/ui/streamlit_app.py \
			--server.port $(UI_PORT) \
			--server.headless true \
			> $(UI_LOG) 2>&1 & \
		echo $$! > $(UI_PID); \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
			sleep 1; \
			if curl -s http://localhost:$(UI_PORT)/_stcore/health >/dev/null 2>&1; then \
				echo -e "$(GREEN)OK$(NC) (PID $$(cat $(UI_PID)), port $(UI_PORT))"; \
				break; \
			fi; \
			if [ $$i -eq 10 ]; then \
				echo -e "$(RED)FAILED$(NC) — check $(UI_LOG)"; \
				exit 1; \
			fi; \
		done; \
	fi

# -------------------------------------------------------------------
# All-in-one
# -------------------------------------------------------------------
run: check-env ## Start all services with confirmation at each step
	@echo ""
	@$(MAKE) --no-print-directory kill-orphans
	@echo ""
	@echo "  Starting AML Pipeline services..."
	@echo "  =================================="
	@$(MAKE) --no-print-directory redis
	@$(MAKE) --no-print-directory api
	@$(MAKE) --no-print-directory celery
	@$(MAKE) --no-print-directory ui
	@echo ""
	@echo "  =================================="
	@echo -e "  $(GREEN)All services running!$(NC)"
	@echo ""
	@echo -e "  Streamlit UI:  $(CYAN)http://localhost:$(UI_PORT)$(NC)"
	@echo -e "  API Docs:      $(CYAN)http://localhost:$(API_PORT)/docs$(NC)"
	@echo -e "  API Health:    $(CYAN)http://localhost:$(API_PORT)/status/health$(NC)"
	@echo ""
	@echo "  Run 'make status' to check services"
	@echo "  Run 'make stop' to stop everything"
	@echo "  Run 'make logs' to tail all logs"
	@echo ""

# -------------------------------------------------------------------
# Status
# -------------------------------------------------------------------
status: ## Show status of all services
	@echo ""
	@echo "  Service Status"
	@echo "  =============="
	@printf "  %-12s" "Redis:" ; \
		if [ -f $(REDIS_PID) ] && kill -0 $$(cat $(REDIS_PID)) 2>/dev/null; then \
			echo -e "$(GREEN)running$(NC) (PID $$(cat $(REDIS_PID)))"; \
		else \
			echo -e "$(RED)stopped$(NC)"; \
		fi
	@printf "  %-12s" "API:" ; \
		if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then \
			echo -e "$(GREEN)running$(NC) (PID $$(cat $(API_PID)), port $(API_PORT))"; \
		else \
			echo -e "$(RED)stopped$(NC)"; \
		fi
	@printf "  %-12s" "Celery:" ; \
		if [ -f $(CELERY_PID) ] && kill -0 $$(cat $(CELERY_PID)) 2>/dev/null; then \
			echo -e "$(GREEN)running$(NC) (PID $$(cat $(CELERY_PID)))"; \
		else \
			echo -e "$(RED)stopped$(NC)"; \
		fi
	@printf "  %-12s" "Streamlit:" ; \
		if [ -f $(UI_PID) ] && kill -0 $$(cat $(UI_PID)) 2>/dev/null; then \
			echo -e "$(GREEN)running$(NC) (PID $$(cat $(UI_PID)), port $(UI_PORT))"; \
		else \
			echo -e "$(RED)stopped$(NC)"; \
		fi
	@echo ""

# -------------------------------------------------------------------
# Stop
# -------------------------------------------------------------------
stop: ## Stop all services
	@echo ""
	@echo "  Stopping services..."
	@for svc_name in Streamlit Celery API Redis; do \
		case $$svc_name in \
			Streamlit) pidfile=$(UI_PID) ;; \
			Celery)    pidfile=$(CELERY_PID) ;; \
			API)       pidfile=$(API_PID) ;; \
			Redis)     pidfile=$(REDIS_PID) ;; \
		esac; \
		printf "  %-12s" "$$svc_name:" ; \
		if [ -f $$pidfile ] && kill -0 $$(cat $$pidfile) 2>/dev/null; then \
			kill $$(cat $$pidfile) 2>/dev/null; \
			sleep 1; \
			if kill -0 $$(cat $$pidfile) 2>/dev/null; then \
				kill -9 $$(cat $$pidfile) 2>/dev/null; \
			fi; \
			rm -f $$pidfile; \
			echo -e "$(GREEN)stopped$(NC)"; \
		else \
			rm -f $$pidfile; \
			echo -e "$(YELLOW)not running$(NC)"; \
		fi; \
	done
	@# Also kill any orphan processes missed by PID files
	@fuser -k $(API_PORT)/tcp 2>/dev/null && echo -e "  $(GREEN)Killed orphan on port $(API_PORT)$(NC)" || true
	@fuser -k $(UI_PORT)/tcp 2>/dev/null && echo -e "  $(GREEN)Killed orphan on port $(UI_PORT)$(NC)" || true
	@pgrep -f '[c]elery.*app.workers' 2>/dev/null | xargs -r kill -9 2>/dev/null \
		&& echo -e "  $(GREEN)Killed orphan celery$(NC)" || true
	@echo ""

# -------------------------------------------------------------------
# Logs
# -------------------------------------------------------------------
logs: ## Tail all service logs
	@echo "  Tailing logs (Ctrl+C to stop)..."
	@tail -f $(LOG_DIR)/*.log 2>/dev/null || echo "  No log files found. Run 'make run' first."

# -------------------------------------------------------------------
# Clean
# -------------------------------------------------------------------
clean: stop ## Stop all services and remove log files
	@rm -rf $(LOG_DIR)
	@echo -e "  $(GREEN)Cleaned up log directory$(NC)"
