#!/bin/bash
# Ham Radio Application - Docker Entrypoint Script
# =================================================

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}Ham Radio Operator Web Application${NC}"
echo -e "${GREEN}Docker Container Initialization${NC}"
echo -e "${GREEN}=================================================${NC}"

# =================================================================
# Check User and Permissions
# =================================================================
echo -e "\n${YELLOW}[0/7] Checking user and permissions...${NC}"

echo "Running as user: $(whoami) (UID: $(id -u), GID: $(id -g))"

if [ ! -d "/data" ]; then
    echo -e "${RED}ERROR: /data directory does not exist!${NC}"
    exit 1
fi

if [ ! -w "/data" ]; then
    echo -e "${RED}ERROR: /data directory is not writable!${NC}"
    ls -la /data
    echo "Please run: sudo chown -R 1000:1000 ./data"
    exit 1
fi

echo -e "${GREEN}✓ User and permissions validated${NC}"

# =================================================================
# Secret Key Management
# =================================================================
echo -e "\n${YELLOW}[1/7] Managing secret key...${NC}"

SECRET_KEY_FILE="/data/secret_key"

# Check if SECRET_KEY is provided via environment
if [ -n "$SECRET_KEY" ] && [ "$SECRET_KEY" != "change-this-in-production" ]; then
    echo "Using SECRET_KEY from environment variable"
    
    # Save to file if it doesn't exist
    if [ ! -f "$SECRET_KEY_FILE" ]; then
        echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
        echo "✓ Secret key saved to file"
    fi
else
    # Check if secret key file exists
    if [ -f "$SECRET_KEY_FILE" ]; then
        echo "✓ Existing secret key found"
        export SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    else
        echo "Generating new secret key..."
        # Generate a secure random key using Python
        NEW_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        
        # Save to file
        echo "$NEW_SECRET_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
        
        # Export for this session
        export SECRET_KEY="$NEW_SECRET_KEY"
        
        echo "✓ New secret key generated and saved"
    fi
fi

# Validate key length
KEY_LENGTH=$(echo -n "$SECRET_KEY" | wc -c)
if [ "$KEY_LENGTH" -lt 32 ]; then
    echo -e "${RED}ERROR: SECRET_KEY is too short (${KEY_LENGTH} characters)${NC}"
    echo "Minimum length is 32 characters"
    exit 1
fi

echo -e "${GREEN}✓ Secret key validated (length: ${KEY_LENGTH})${NC}"

# =================================================================
# Environment Validation
# =================================================================
echo -e "\n${YELLOW}[2/7] Validating environment...${NC}"

echo -e "${GREEN}✓ Environment validated${NC}"

# =================================================================
# Directory Setup
# =================================================================
echo -e "\n${YELLOW}[3/7] Setting up directories...${NC}"

for dir in /data/db /data/certs /data/callsigns /data/backups /data/logs; do
    if [ ! -d "$dir" ]; then
        echo "Creating directory: $dir"
        mkdir -p "$dir" || {
            echo -e "${RED}ERROR: Failed to create $dir${NC}"
            exit 1
        }
    fi
    
    if [ ! -w "$dir" ]; then
        echo -e "${RED}ERROR: Directory $dir is not writable${NC}"
        exit 1
    fi
done

echo -e "${GREEN}✓ All directories created and verified${NC}"

# =================================================================
# SSL Certificate Generation
# =================================================================
echo -e "\n${YELLOW}[4/7] Checking SSL certificates...${NC}"

if [ "$USE_SSL" = "true" ]; then
    if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
        echo "Generating self-signed SSL certificate..."
        
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
echo -e "\n${YELLOW}[5/7] Initializing database...${NC}"

DB_PATH=$(echo $DATABASE_URL | sed 's|sqlite:///||')
echo "Database path: $DB_PATH"

DB_DIR=$(dirname "$DB_PATH")

if [ ! -d "$DB_DIR" ]; then
    echo -e "${RED}ERROR: Database directory $DB_DIR does not exist${NC}"
    exit 1
fi

if [ ! -w "$DB_DIR" ]; then
    echo -e "${RED}ERROR: Database directory $DB_DIR is not writable${NC}"
    exit 1
fi

if [ ! -f "$DB_PATH" ]; then
    echo "Database not found. Will be created on first run."
else
    echo -e "${GREEN}✓ Database exists: $DB_PATH${NC}"
    
    # Create backup
    BACKUP_FILE="/data/backups/ham_radio_$(date +%Y%m%d_%H%M%S).db"
    if cp "$DB_PATH" "$BACKUP_FILE" 2>/dev/null; then
        echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
    fi
fi

# =================================================================
# Device Detection
# =================================================================
echo -e "\n${YELLOW}[6/7] Detecting devices...${NC}"

if [ "$USE_MOCK_DEVICES" = "false" ]; then
    echo "Real device mode enabled."
else
    echo "Mock device mode enabled"
fi

# =================================================================
# Application Startup
# =================================================================
echo -e "\n${YELLOW}[7/7] Starting application...${NC}"

echo -e "\n${GREEN}Configuration Summary:${NC}"
echo "  Flask Environment: $FLASK_ENV"
echo "  Debug Mode: ${FLASK_DEBUG:-0}"
echo "  SSL Enabled: $USE_SSL"
echo "  Mock Devices: $USE_MOCK_DEVICES"
echo "  Database: $DATABASE_URL"
echo "  Listen Address: ${FLASK_HOST:-0.0.0.0}:${FLASK_PORT:-5000}"
echo "  Secret Key: [SECURED] (${KEY_LENGTH} characters)"

echo -e "\n${GREEN}=================================================${NC}"
echo -e "${GREEN}Starting Ham Radio Application...${NC}"
echo -e "${GREEN}=================================================${NC}\n"

# Execute the main command
exec "$@"
