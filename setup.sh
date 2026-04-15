#!/bin/bash
# Ham Radio Application - Initial Setup Script
# =============================================
# Run this script for first-time setup

set -e

echo "================================================="
echo "Ham Radio Application - Docker Setup"
echo "================================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "ERROR: Docker Compose is not installed"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✓ Docker and Docker Compose are installed"
echo ""

# Create necessary directories
echo "Creating data directories..."
mkdir -p data/db
mkdir -p data/certs
mkdir -p data/backups
mkdir -p data/callsigns
mkdir -p data/logs
mkdir -p plugins/implementations

echo "✓ Directories created"
echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    
    # Generate a secure SECRET_KEY
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    
    # Update .env with generated key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
    else
        # Linux
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
    fi
    
    echo "✓ .env file created with secure SECRET_KEY"
    echo ""
    echo "IMPORTANT: Review and customize .env file for your setup"
    echo ""
else
    echo "✓ .env file already exists"
    echo ""
fi

# Make entrypoint script executable
if [ -f docker-entrypoint.sh ]; then
    chmod +x docker-entrypoint.sh
    echo "✓ Entrypoint script permissions set"
    echo ""
fi

# Build the Docker image
echo "Building Docker image..."
docker-compose build

echo ""
echo "================================================="
echo "Setup Complete!"
echo "================================================="
echo ""
echo "Next steps:"
echo "  1. Review and customize .env file"
echo "  2. Start the application: docker-compose up -d"
echo "  3. View logs: docker-compose logs -f app"
echo "  4. Access at: http://localhost:5000"
echo ""
echo "For device access (GPS, Radio, SDR):"
echo "  - Set USE_MOCK_DEVICES=false in .env"
echo "  - Ensure USB devices are connected"
echo "  - Update device paths in .env if needed"
echo ""
echo "73! (Best regards)"
