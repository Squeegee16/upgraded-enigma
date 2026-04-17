#!/bin/bash
# Ham Radio Application - Docker Entrypoint Script
# =================================================
# This script runs before the main application starts
# It handles initialization, configuration, and setup

set -e  # Exit on error

# Color output for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}Ham Radio Operator Web Application${NC}"
echo -e "${GREEN}Docker Container Initialization${NC}"
echo -e "${GREEN}=================================================${NC}"

# =================================================================
# Check User and Permissions
# =================================================================
echo -e "\n${YELLOW}[0/6] Checking user and permissions...${NC}"

echo "Running as user: $(whoami) (UID: $(id -u), GID: $(id -g))"

# Check if /data exists and is writable
if [ ! -d "/data" ]; then
    echo -e "${RED}ERROR: /data directory does not exist!${NC}"
    echo "This should have been created in the Dockerfile."
    exit 1
fi

# Test write permissions
if [ ! -w "/data" ]; then
    echo -e "${RED}ERROR: /data directory is not writable!${NC}"
    echo "Current permissions:"
    ls -la /data
    echo ""
    echo "Please ensure the volume is mounted with correct permissions."
    echo "On the host, run: sudo chown -R 1000:1000 ./data"
    exit 1
fi

echo -e "${GREEN}✓ User and permissions validated${NC}"

# =================================================================
# Environment Validation
# =================================================================
echo -e "\n${YELLOW}[1/6] Validating environment...${NC}"

# Check if SECRET_KEY is set and not default
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "change-this-in-production" ]; then
    echo -e "${RED}WARNING: SECRET_KEY is not set or using default value!${NC}"
    echo -e "${RED}This is a security risk in production.${NC}"
    if [ "$FLASK_ENV" = "production" ]; then
        echo -e "${RED}Exiting. Please set a secure SECRET_KEY.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓ Environment validated${NC}"

# =================================================================
# Directory Setup
# =================================================================
echo -e "\n${YELLOW}[2/6] Setting up directories...${NC}"

# Create necessary directories with error checking
for dir in /data/db /data/certs /data/callsigns /data/backups /data/logs; do
    if [ ! -d "$dir" ]; then
        echo "Creating directory: $dir"
        mkdir -p "$dir" || {
            echo -e "${RED}ERROR: Failed to create $dir${NC}"
            exit 1
        }
    fi
    
    # Verify directory is writable
    if [ ! -w "$dir" ]; then
        echo -e "${RED}ERROR: Directory $dir is not writable${NC}"
        ls -la "$dir"
        exit 1
    fi
done

echo -e "${GREEN}✓ All directories created and verified${NC}"

# =================================================================
# SSL Certificate Generation
# =================================================================
echo -e "\n${YELLOW}[3/6] Checking SSL certificates...${NC}"

if [ "$USE_SSL" = "true" ]; then
    if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
        echo "SSL enabled but certificates not found. Generating self-signed certificate..."
        
        # Check if openssl is available
        if ! command -v openssl &> /dev/null; then
            echo -e "${RED}ERROR: openssl not found. Cannot generate SSL certificate.${NC}"
            echo "Installing openssl..."
            apt-get update && apt-get install -y openssl
        fi
        
        openssl req -x509 -newkey rsa:4096 -nodes \
            -out "$SSL_CERT" \
            -keyout "$SSL_KEY" \
            -days 365 \
            -subj "/C=US/ST=State/L=City/O=HamRadio/OU=App/CN=localhost" \
            2>/dev/null || {
                echo -e "${RED}ERROR: Failed to generate SSL certificate${NC}"
                exit 1
            }
        
        chmod 644 "$SSL_CERT"
        chmod 600 "$SSL_KEY"
        
        echo -e "${GREEN}✓ Self-signed SSL certificate generated${NC}"
    else
        echo -e "${GREEN}✓ SSL certificates found${NC}"
    fi
else
    echo "SSL disabled"
fi

# =================================================================
# Database Initialization
# =================================================================
echo -e "\n${YELLOW}[4/6] Initializing database...${NC}"

# Display database configuration
echo "Database URL: $DATABASE_URL"
DB_PATH=$(echo $DATABASE_URL | sed 's|sqlite:///||')
echo "Database file path: $DB_PATH"

# Check if database directory exists and is writable
DB_DIR=$(dirname "$DB_PATH")
echo "Database directory: $DB_DIR"

if [ ! -d "$DB_DIR" ]; then
    echo -e "${RED}ERROR: Database directory $DB_DIR does not exist${NC}"
    exit 1
fi

if [ ! -w "$DB_DIR" ]; then
    echo -e "${RED}ERROR: Database directory $DB_DIR is not writable${NC}"
    ls -la "$DB_DIR"
    exit 1
fi

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "Database not found. Will be created on first run."
    echo "Testing database creation..."
    
    # Create a test file to verify write permissions
    TEST_FILE="${DB_DIR}/.test_write"
    if touch "$TEST_FILE" 2>/dev/null; then
        rm "$TEST_FILE"
        echo -e "${GREEN}✓ Database directory is writable${NC}"
    else
        echo -e "${RED}ERROR: Cannot write to database directory${NC}"
        ls -la "$DB_DIR"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Database exists: $DB_PATH${NC}"
    
    # Create backup before starting
    BACKUP_FILE="/data/backups/ham_radio_$(date +%Y%m%d_%H%M%S).db"
    if cp "$DB_PATH" "$BACKUP_FILE" 2>/dev/null; then
        echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
    else
        echo -e "${YELLOW}⚠ Could not create backup${NC}"
    fi
fi

# =================================================================
# Device Detection
# =================================================================
echo -e "\n${YELLOW}[5/6] Detecting devices...${NC}"

if [ "$USE_MOCK_DEVICES" = "false" ]; then
    echo "Real device mode enabled. Checking for devices..."
    
    # Check GPS device
    if [ -e "$GPS_SERIAL_PORT" ]; then
        echo -e "${GREEN}✓ GPS device found: $GPS_SERIAL_PORT${NC}"
    else
        echo -e "${YELLOW}⚠ GPS device not found: $GPS_SERIAL_PORT${NC}"
        echo "  Falling back to mock GPS"
    fi
    
    # Check Radio device
    if [ -e "$RADIO_PORT" ]; then
        echo -e "${GREEN}✓ Radio device found: $RADIO_PORT${NC}"
    else
        echo -e "${YELLOW}⚠ Radio device not found: $RADIO_PORT${NC}"
        echo "  Falling back to mock radio"
    fi
    
    # Check RTL-SDR
    if lsusb 2>/dev/null | grep -q "RTL"; then
        echo -e "${GREEN}✓ RTL-SDR device detected${NC}"
    else
        echo -e "${YELLOW}⚠ RTL-SDR device not detected${NC}"
        echo "  Falling back to mock SDR"
    fi
else
    echo "Mock device mode enabled (USE_MOCK_DEVICES=true)"
    echo "All device interfaces will use mock implementations"
fi

# =================================================================
# Application Startup
# =================================================================
echo -e "\n${YELLOW}[6/6] Starting application...${NC}"

# Display configuration summary
echo -e "\n${GREEN}Configuration Summary:${NC}"
echo "  Flask Environment: $FLASK_ENV"
echo "  Debug Mode: ${FLASK_DEBUG:-0}"
echo "  SSL Enabled: $USE_SSL"
echo "  Mock Devices: $USE_MOCK_DEVICES"
echo "  Database: $DATABASE_URL"
echo "  Listen Address: ${FLASK_HOST:-0.0.0.0}:${FLASK_PORT:-5000}"

# Final permission check
echo -e "\n${YELLOW}Final permission check:${NC}"
ls -la /data/
ls -la /data/db/ 2>/dev/null || echo "  /data/db/ will be populated by application"

echo -e "\n${GREEN}=================================================${NC}"
echo -e "${GREEN}Starting Ham Radio Application...${NC}"
echo -e "${GREEN}=================================================${NC}\n"

# Execute the main command (passed as arguments to this script)
exec "$@"
