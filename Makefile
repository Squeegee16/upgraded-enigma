# Ham Radio Application - Makefile
# =================================
# Convenience commands for common Docker operations

.PHONY: help build up down logs shell backup restore clean

# Default target
.DEFAULT_GOAL := help

# Variables
COMPOSE := docker-compose
APP_CONTAINER := hamradio_app
BACKUP_DIR := ./data/backups

# Help target - displays available commands
help:
	@echo "Ham Radio Application - Docker Commands"
	@echo "========================================"
	@echo ""
	@echo "Available commands:"
	@echo "  make build     - Build the Docker image"
	@echo "  make up        - Start the application"
	@echo "  make down      - Stop the application"
	@echo "  make restart   - Restart the application"
	@echo "  make logs      - View application logs"
	@echo "  make shell     - Access container shell"
	@echo "  make backup    - Create database backup"
	@echo "  make restore   - Restore from backup"
	@echo "  make clean     - Remove containers and volumes"
	@echo "  make ps        - Show running containers"
	@echo "  make stats     - Show container resource usage"
	@echo ""

# Build the Docker image
build:
	@echo "Building Docker image..."
	$(COMPOSE) build --no-cache

# Start the application
up:
	@echo "Starting Ham Radio Application..."
	mkdir -p data/db data/certs data/backups data/callsigns
	$(COMPOSE) up -d
	@echo "Application started!"
	@echo "Access at: http://localhost:5000"

# Stop the application
down:
	@echo "Stopping Ham Radio Application..."
	$(COMPOSE) down

# Restart the application
restart: down up

# View logs
logs:
	$(COMPOSE) logs -f app

# Access container shell
shell:
	$(COMPOSE) exec app bash

# Create manual backup
backup:
	@echo "Creating database backup..."
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
	$(COMPOSE) exec app cp /data/db/ham_radio.db /data/backups/ham_radio_$$TIMESTAMP.db
	@echo "Backup created in $(BACKUP_DIR)"

# Restore from backup
restore:
	@echo "Available backups:"
	@ls -1 $(BACKUP_DIR)
	@read -p "Enter backup filename to restore: " BACKUP_FILE; \
	$(COMPOSE) exec app cp /data/backups/$$BACKUP_FILE /data/db/ham_radio.db
	@echo "Database restored. Restarting application..."
	$(MAKE) restart

# Clean up containers and volumes
clean:
	@echo "WARNING: This will remove all containers and data!"
	@read -p "Are you sure? (yes/no): " CONFIRM; \
	if [ "$$CONFIRM" = "yes" ]; then \
		$(COMPOSE) down -v; \
		echo "Cleanup complete"; \
	else \
		echo "Cancelled"; \
	fi

# Show running containers
ps:
	$(COMPOSE) ps

# Show container resource usage
stats:
	docker stats $(APP_CONTAINER)

# Pull latest base images
pull:
	$(COMPOSE) pull

# Update application (pull, build, restart)
update: pull build restart
	@echo "Application updated!"
