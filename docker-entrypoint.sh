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

# Create necessary directories
mkdir -p /data/db
mkdir -p /data/certs
mkdir -p /data/callsigns
mkdir -p /data/backups
mkdir -p /data/logs

# Set proper permissions
chmod 755 /data/db
chmod 755 /data/certs
chmod 755 /data/backups

echo -e "${GREEN}✓ Directories created${NC}"

# =================================================================
# SSL Certificate Generation
# =================================================================
echo -e "\n${YELLOW}[3/6] Checking SSL certificates...${NC}"

if [ "$USE_SSL" = "true" ]; then
    if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
        echo "SSL enabled but certificates not found. Generating self-signed certificate..."
        
        openssl req -x509 -newkey rsa:4096 -nodes \
            -out "$SSL_CERT" \
            -keyout "$SSL_KEY" \
            -days 365 \
            -subj "/C=US/ST=State/L=City/O=HamRadio/OU=App/CN=localhost" \
            2>/dev/null
        
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

# Check if database exists
if [ ! -f "/data/db/ham_radio.db" ]; then
    echo "Database not found. Will be created on first run."
else
    echo -e "${GREEN}✓ Database exists${NC}"
    
    # Create backup before starting
    BACKUP_FILE="/data/backups/ham_radio_$(date +%Y%m%d_%H%M%S).db"
    cp /data/db/ham_radio.db "$BACKUP_FILE"
    echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
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
    if lsusb | grep -q "RTL"; then
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
echo "  Debug Mode: $FLASK_DEBUG"
echo "  SSL Enabled: $USE_SSL"
echo "  Mock Devices: $USE_MOCK_DEVICES"
echo "  Database: $DATABASE_URL"
echo "  Listen Address: $FLASK_HOST:$FLASK_PORT"

echo -e "\n${GREEN}=================================================${NC}"
echo -e "${GREEN}Starting Ham Radio Application...${NC}"
echo -e "${GREEN}=================================================${NC}\n"

# Execute the main command (passed as arguments to this script)
exec "$@"
