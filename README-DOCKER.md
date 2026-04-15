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
