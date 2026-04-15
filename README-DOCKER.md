# Ham Radio Application - Docker Deployment Guide

## Quick Start

### 1. Prerequisites

- Docker 20.10 or higher
- Docker Compose 2.0 or higher
- 2GB free disk space
- (Optional) USB devices: GPS, Radio, RTL-SDR

### 2. Initial Setup

```bash
# Clone or extract the application
cd ham_radio_app

# Run setup script
chmod +x setup.sh
./setup.sh

# Review and customize configuration
nano .env



#Docker Stuff
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f app

# Access the application
# Open browser: http://localhost:5000
# Or with SSL: https://localhost:5443

# Stop containers
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v

# Application
FLASK_ENV=production
SECRET_KEY=your-secure-key-here

# Devices
USE_MOCK_DEVICES=true  # Set false for real hardware

# SSL
USE_SSL=true

Device Access
For real hardware access:

Set USE_MOCK_DEVICES=false in .env
Connect USB devices
Find device paths: ls -l /dev/ttyUSB*
Update device paths in .env
Restart: docker-compose restart
Data Persistence
Data is stored in ./data/ directory:
data/
├── db/          # SQLite database
├── certs/       # SSL certificates
├── backups/     # Automated backups
├── callsigns/   # Callsign database
└── logs/        # Application logs

#Common Operations
# All logs
docker-compose logs -f

# Application logs only
docker-compose logs -f app

# Last 100 lines
docker-compose logs --tail=100 app

##Access Container Shell
docker-compose exec app bash

##Manual Backup
# Using make
make backup
# Or directly
docker-compose exec app cp /data/db/ham_radio.db /data/backups/backup_$(date +%Y%m%d).db

## Restore
# Stop application
docker-compose down

# Restore database file
cp data/backups/backup_YYYYMMDD.db data/db/ham_radio.db

# Start application
docker-compose up -d

##Update Application
# Pull latest code
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d

Troubleshooting
Container Won't Start
docker-compose logs app

# Verify configuration
cat .env

# Check permissions
ls -la data/

Database Issues
# Reset database (WARNING: deletes all data)
docker-compose down
rm data/db/ham_radio.db
docker-compose up -d

Device Not Found
# List USB devices
ls -l /dev/ttyUSB*
lsusb

# Check device permissions
docker-compose exec app ls -l /dev/ttyUSB0

# Add user to dialout group (on host)
sudo usermod -aG dialout $USER
# Logout and login again

Recommended Configuration
yaml
Copy code
Download
# docker-compose.yml additions for production

services:
  app:
    restart: always
    
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
yaml
Behind Reverse Proxy
Example Nginx configuration:

nginx
server {
    listen 80;
    server_name hamradio.example.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
nginx

Advanced Usage
Custom Plugins
bash
Copy code
Download
# Add plugin to implementations directory
cp my_plugin.py plugins/implementations/

# Restart application
docker-compose restart app

Multiple Instances

# Copy directory
cp -r ham_radio_app ham_radio_app2

# Edit docker-compose.yml - change ports and container names
# Start second instance
cd ham_radio_app2
docker-compose up -d

Resource Monitoring

# Container stats
docker stats hamradio_app

# Disk usage
docker system df

# Clean unused resources
docker system prune -a
