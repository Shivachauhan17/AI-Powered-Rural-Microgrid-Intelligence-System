.PHONY: help dev build push deploy clean test

help:
	@echo "⚡ AI Microgrid System - Available Commands"
	@echo "─────────────────────────────────────────"
	@echo "  make dev       - Run locally with Docker Compose"
	@echo "  make build     - Build Docker images"
	@echo "  make deploy    - Deploy to AWS ECS"
	@echo "  make test      - Run backend tests"
	@echo "  make clean     - Remove containers and volumes"
	@echo "  make logs      - Tail container logs"

dev:
	cp -n .env.example .env || true
	docker compose up --build

build:
	docker compose build

test:
	cd backend && pip install pytest -q && pytest -v

deploy:
	chmod +x infra/aws/deploy.sh
	./infra/aws/deploy.sh

logs:
	docker compose logs -f

clean:
	docker compose down -v --remove-orphans
	docker system prune -f
