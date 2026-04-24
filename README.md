<div align="left">
<code>
    ooooo   ooooo       .o.       ooo        ooooo    ooooooooo.         .o.       oooooooooo.
    `888'   `888'      .888.      `88.       .888'    `888   `Y88.      .888.      `888'   `Y8b
     888     888      .8"888.      888b     d'888      888   .d88'     .8"888.      888      888
     888ooooo888     .8' `888.     8 Y88. .P  888      888ooo88P'     .8' `888.     888      888
     888     888    .88ooo8888.    8  `888'   888      888`88b.      .88ooo8888.    888      888
     888     888   .8'     `888.   8    Y     888      888  `88b.   .8'     `888.   888     d88'
    o888o   o888o o88o     o8888o o8o        o888o    o888o  o888o o88o     o8888o o888bood8P'
</code>
<code>
    ··················································································
    : ooooooooo.   ooooo   .oooooo.              .oooooo.   ooooooooo.    .oooooo..o :
    : `888   `Y88. `888'  d8P'  `Y8b            d8P'  `Y8b  `888   `Y88. d8P'    `Y8 :
    :  888   .d88'  888  888                   888      888  888   .d88' Y88bo.      :
    :  888ooo88P'   888  888                   888      888  888ooo88P'   `"Y8888o.  :
    :  888`88b.     888  888     ooooo 8888888 888      888  888              `"Y88b :
    :  888  `88b.   888  `88.    .88'          `88b    d88'  888         oo     .d8P :
    : o888o  o888o o888o  `Y8bood8P'            `Y8bood8P'  o888o        8""88888P'  :
    ··················································································
</code>
<h2>
    <p> A modular, web-based ham radio station control and logging application for Linux</p>
</h2>
<img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python" alt="Python" class="my-2 rounded-lg max-w-full" loading="lazy">
<img src="https://img.shields.io/badge/Flask-3.0-green?logo=flask" alt="Flask" class="my-2 rounded-lg max-w-full" loading="lazy">
<img src="https://img.shields.io/badge/Docker-Supported-blue?logo=docker" alt="Docker" class="my-2 rounded-lg max-w-full" loading="lazy">
<img src="https://img.shields.io/badge/Platform-Linux-orange?logo=linux" alt="Platform" class="my-2 rounded-lg max-w-full" loading="lazy">
</div>

### Table of Contents
#### Overview
#### Features
#### Hardware Requirements
#### Software Requirements
#### Quick Start
#### Installation
#### Standard Installation
#### Docker Installation
#### Configuration
#### Available Plugins
#### Installing Plugins
#### Canadian Callsign Database
#### Accessing the Application
#### Troubleshooting
#### Contributing
#### License

## Overview
Ham Radio App is a Linux-based, web-accessible station control application for amateur radio operators. It runs on a local WiFi hotspot and is accessible from any laptop or tablet on the network. The application uses a modular plugin architecture allowing integration with popular ham radio software including FLdigi, WSJT-X, Winlink, QSSTV, SatDump, and more.
<details>
```scss
┌──────────────────────────────────────────────────────────────┐
│                    WiFi Hotspot Network                      │
│--------------------------------------------------------------│
│   ┌──────────┐    ┌──────────┐    ┌───────────────────────┐  │
│   │ Laptop   │    │  Tablet  │    │   Ham Radio Server    │  │
│   │          │    │          │    │                       │  │
│   │ Browser  │◄──►│ Browser  │◄──►│  Flask Web App        │  │
│   └──────────┘    └──────────┘    │                       │  │
│                                   │  ┌─────────────────┐  │  │
│                                   │  │    Plugins      │  │  │
│                                   │  │ FLdigi  WSJTX   │  │  │
│                                   │  │ Winlink QSSTV   │  │  │
│                                   │  │ SatDump GrayWolf│  │  │
│                                   │  └─────────────────┘  │  │
│                                   │                       │  │
│                                   │  ┌────────────────┐   │  │
│                                   │  │    Devices     │   │  │
│                                   │  │ RTL-SDR  GPS   │   │  │
│                                   │  │ Yaesu FT-891   │   │  │
│                                   │  └────────────────┘   │  │
│                                   └───────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```
</details>

## Features
<details>
    
### 🔐 User Management
    Secure user registration and login with session management
    Bcrypt password hashing with strength enforcement
    Callsign format validation (international formats)
    Canadian ISED callsign database validation with name and qualification display
    Registration validated against the official ISED amateur radio database
### 📊 DashboardReal-time UTC clock display
    Live GPS location and Maidenhead grid square
    Connected device status (GPS, Radio, RTL-SDR)
    Plugin status overview with one-click launch buttons
    Operator name and qualification display from ISED database
    Recent contacts summary
### 📖 Central Logbook
    Log contacts with callsign, mode, band, frequency, grid, RST, and notes
    Filter and search by any field
    Export in ADIF, CSV, and JSON formats
    Contact statistics (by mode, band, unique callsigns)
    Paginated contact list
## 🔌 Plugin Architecture
    Automatic plugin discovery on startup
    First-run dependency installation for each plugin
    Each plugin has its own dedicated UI page
    All plugins integrate with the central logbook
    GPS and radio device data shared across all plugins
## 🛰️ Device Integration
    RTL-SDR (via rtl-sdr tools and direct USB)
    Serial GPS (NMEA protocol, any USB GPS dongle)
    Yaesu FT-891 (via Hamlib — compatible with 400+ radios)
    Mock device mode for development and testing without hardware
## 🔒 Security
    HTTPS with self-signed certificate (generated automatically)
    CSRF protection on all forms
    Session-based authentication
    Input sanitisation throughout
    Non-root Docker container execution
## 🐳 Docker Support
    Multi-stage Docker build for minimal image size
    Docker Compose with persistent volumes
    Automated database backup service
    Device passthrough for USB hardware
</details>

## Hardware Requirements

| Minimum (Software / Testing) | Component | Requirement |
| --- | --- | --- |
| CPU | 1 GHz single-core | (x86_64 or ARM) |
| RAM | 512 MB |
| Storage | 4 GB free |
| Network | WiFi adapter | (hotspot capable) |
| OS | Any Linux distribution | Debian, Ubuntu, Raspberry Pi OS, etc. |


## Recommended (Full Station)

| Component | Requirement |
| --- | --- |
| CPU | Quad-core 1.5 GHz+ (Raspberry Pi 4 or better)|
| RAM | 2 GB+ |
| Storage |16 GB+  SSD preferred |
| Network | Dual-band WiFi adapter or dedicated WiFi dongle |
| OS | Ubuntu 22.04 LTS / Debian 12 / Raspberry Pi OS 64-bit |

## Optional Hardware (for Plugin Features)
<details>
| Device | Purpose | Notes |
| --- | --- | --- |
| RTL-SDR v3 dongle | SDR receiver | Required for SDR/satellite plugins |
| USB GPS receiver | Position reporting, grid square | Any NMEA-compatible USB GPS|
| Yaesu FT-891 | HF radio control | Any Hamlib-compatible radio works |
| USB Serial adapter | Radio CAT control | If radio uses RS-232 |
| SMA antenna| SDR reception | Dipole for VHF, whip for HF |
| VHF/UHF antenna | 137 MHz weather satellites | V-dipole or QFH recommended |
| L-Band antenna | 1.7 GHz satellite imagery | Patch antenna required |
</details>

## Software Requirements
#### Operating System
    Linux (any modern distribution)
    Tested on: Ubuntu 22.04, Debian 12, Raspberry Pi OS (64-bit)
#### Required Software Package	Version	Purpose
    Python	3.8+    Application runtime
    pip	Latest    Python package management
    git    Any	Installation and updates
    openssl    Any	SSL certificate generation
### Required Python Packages
#### Installed automatically during setup
    Flask==3.0.0
    Flask-Login==0.6.3
    Flask-WTF==1.2.1
    Flask-SQLAlchemy==3.1.1
    WTForms==3.1.1
    bcrypt==4.1.2
    pyserial==3.5
    pynmea2==1.18.0
    requests==2.31.0
    pyopenssl==23.3.0
    numpy==1.24.3
    Pillow==10.0.0
    watchdog==3.0.0
    psutil==5.9.5

## Radio control via Hamlib
    sudo apt-get install hamlib-utils
## RTL-SDR support
    sudo apt-get install rtl-sdr
## GPS support
    sudo apt-get install gpsd gpsd-clients
## For building plugins from source
    sudo apt-get install build-essential cmake git

## Quick Start
### 1. Clone the repository
    git clone https://github.com/yourusername/ham-radio-app.git
    cd ham-radio-app

### 2. Run the setup script
    chmod +x setup.sh
    ./setup.sh

### 3. Start the application
    source venv/bin/activate
    python app.py

### 4. Open your browser to:
    https://localhost:5000

## Installation
### Standard Installation
<details>
    
#### Step 1 — Install System Dependencies
##### Ubuntu / Debian / Raspberry Pi OS:
    sudo apt-get update
    sudo apt-get install -y \
    python3 python3-pip python3-venv \
    git openssl \
    hamlib-utils rtl-sdr gpsd gpsd-clients \
    build-essential cmake

##### Fedora / RHEL:
    sudo dnf install -y \
    python3 python3-pip \
    git openssl \
    hamlib hamlib-utils \
    rtl-sdr

##### Arch Linux:
    sudo pacman -S python python-pip git openssl hamlib rtl-sdr gpsd

#### Step 2 — Clone the Repository
    git clone https://github.com/yourusername/ham-radio-app.git
    cd ham-radio-app

#### Step 3 — Create Python Virtual Environment
    python3 -m venv venv
    source venv/bin/activate
    
#### Step 4 — Install Python Dependencies
    pip install --upgrade pip
    pip install -r requirements.txt
#### Step 5 — Create Data Directories
    mkdir -p data/db data/certs data/backups data/callsigns data/logs
#### Step 6 — Configure the Application
##### Copy the example environment file:
    cp .env.example .env
##### Edit .env with your settings:
    nano .env
##### Key settings to review:

###### Flask environment
    FLASK_ENV=production
###### Device settings
    USE_MOCK_DEVICES=true          # Set false if real hardware connected
    GPS_SERIAL_PORT=/dev/ttyUSB0   # Your GPS serial port
    RADIO_PORT=/dev/ttyUSB1        # Your radio CAT port
    RADIO_MODEL=1035               # Hamlib model (1035 = Yaesu FT-891)

###### SSL (auto-generated if not provided)
    USE_SSL=true

###### Optional: Validate callsigns against Canadian database
    VALIDATE_CALLSIGNS=false

#### Step 7 — Start the Application
    source venv/bin/activate
    python app.py

On first start, the application will:\
✅ Generate a secure secret key automatically\
✅ Create the SQLite database and all tables\
✅ Generate a self-signed SSL certificate\
✅ Connect to configured devices\
✅ Scan and load all plugins\

#### Step 8 — Set Up WiFi Hotspot (Optional)
To share the application over WiFi:
###### Using nmcli (NetworkManager)
    sudo nmcli dev wifi hotspot 
    ssid "HamRadioApp" 
    password "yourpassword" 
    ifname wlan0

###### Clients connect to the hotspot and browse to:
    https://<server-ip>:5000

###### Find your server IP:
    ip addr show wlan0

#### Step 9 — Install as a System Service (Optional)
##### To start automatically on boot:
###### Copy the service file
    sudo cp ham-radio-app.service /etc/systemd/system/
###### Enable and start the service
    sudo systemctl daemon-reload
    sudo systemctl enable ham-radio-app
    sudo systemctl start ham-radio-app

###### Check status
    sudo systemctl status ham-radio-app
</details>

# Docker Installation
<details>
Docker provides an isolated, reproducible environment\
and is the recommended production deployment method.\
### Prerequisites

### Install Docker
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
### Log out and back in

### Install Docker Compose
    sudo apt-get install docker-compose-plugin

#### Step 1 — Clone and Configure
    git clone https://github.com/yourusername/ham-radio-app.git
    cd ham-radio-app
    cp .env.example .env
    nano .env  # Edit your settings

#### Step 2 — Create Data Directories
    mkdir -p data/db data/certs data/backups data/callsigns data/logs

#### Step 3 — Build and Start
##### Build the Docker image
    docker compose build
##### Start all services
    docker compose up -d

##### View logs
    docker compose logs -f app

#### Step 4 — Access the Application
    https://localhost:5000

### Common Docker Commands
#### Stop the application
    docker compose down

#### View application logs
    docker compose logs -f app

#### Access the container shell
    docker compose exec app bash

#### Create a manual database backup
    docker compose exec app cp /data/db/ham_radio.db /data/backups/manual_backup.db

#### Rebuild after code changes
    docker compose build && docker compose up -d

#### Update to latest version
    git pull
    docker compose build --no-cache
    docker compose up -d
</details>

# Raspberry Pi Docker (ARM)
<details>
The application runs on Raspberry Pi 4 with Docker:

### Ensure 64-bit OS (required)
    uname -m  # Should show aarch64

# Build for ARM
    docker compose build
    docker compose up -d

## Configuration
### Environment Variables
    Variable  Default  Description
    FLASK_ENV  development  development or production
    SECRET_KEY  Auto-generated  Session encryption key (auto-created on first run)
    DATABASE_URL	  sqlite:///data/db/ham_radio.db  Database connection string
    USE_MOCK_DEVICES  True  Use simulated devices for testing
    GPS_SERIAL_PORT  /dev/ttyUSB0  GPS device serial port
    GPS_BAUD_RATE  9600  GPS baud rate
    RADIO_MODEL  1035  Hamlib radio model number
    RADIO_PORT  /dev/ttyUSB1  Radio CAT serial port
    RADIO_BAUD_RATE  38400  Radio CAT baud rate
    SDR_DEVICE_INDEX  0  RTL-SDR device index
    USE_SSL  True  Enable HTTPS
    VALIDATE_CALLSIGNS  False  Check Canadian callsign database on registration
    FLASK_HOST  0.0.0.0  Listen address
    FLASK_PORT  5000  Listen port
    TZ  UTC	Server  timezone

### Finding Your Hamlib Radio Model Number
##### List all supported radios
    rigctl --list | grep -i "yaesu\|icom\|kenwood"

#### Common models:
    1035  = Yaesu FT-891
    1022  = Yaesu FT-817/818
    122   = Icom IC-7300
    2014  = Kenwood TS-590S

#### Finding Serial Port Names
##### List USB serial devices
    ls -l /dev/ttyUSB*

##### Check which device is which
    dmesg | grep tty | tail -20

##### Test GPS connection
    cat /dev/ttyUSB0  # Should show NMEA sentences

##### Test radio connection
    rigctl -m 1035 -r /dev/ttyUSB1 f

#### Granting Serial Port Access
#####  Add your user to the dialout group
    sudo usermod -a -G dialout $USER

##### Log out and back in for changes to take effect
##### Or use newgrp:
    newgrp dialout
</details>

### Available Plugins
Plugins are located in plugins/implementations/. Each plugin provides its own UI page accessible from the Dashboard and navigation menu.
<details>
| Plugin | Description | External Software Required | 
| --- | --- | --- |
| FLdigi | Digital modes: PSK31, RTTY, Olivia, MT63, CW, WSPR, and 30+ more | FLdigi |
| WSJT-X | Weak signal modes: FT8, FT4, JT65, JT9, WSPR, Q65, MSK144 | WSJT-X |
| Winlink | Email over radio via Pat Winlink client (Telnet, AX.25, VARA) | Pat Winlink |
| GrayWolf | Winlink gateway client for Linux | GrayWolf |
| OpenWebRX | Multi-user web SDR receiver with waterfall display | OpenWebRX |
| QSSTV | Slow Scan Television (SSTV) receive and transmit | QSSTV |
| SatDump | Weather satellite and GOES/METEOR/NOAA image reception | SatDump |
| SDR Monitor | Real-time spectrum monitoring | sdr-monitor |

### Installing Plugins
Plugins are installed by copying them to the plugins/implementations/ directory. 
Dependencies are installed automatically on first run.

#### Step 1 — Download the Plugin
Download the plugin package you want to install:

##### Example: Download all plugins from the repository
    git clone https://github.com/yourusername/ham-radio-app.git
    ls plugins/implementations/

Or download an individual plugin:

##### Download a specific plugin directory
    (replace 'fldigi' with the plugin name you want)
    cp -r /path/to/plugin/fldigi plugins/implementations/

#### Step 2 — Copy Plugin to the Plugins Directory

##### Navigate to the application directory
    cd ham-radio-app

##### Copy the plugin
    cp -r /path/to/plugin/fldigi plugins/implementations/

##### Verify it was copied
    ls plugins/implementations/

Your plugins/implementations/ directory should look like this:
```scss
plugins/implementations/
├── __init__.py/
├── fldigi/
│   ├── __init__.py
│   ├── plugin.py
│   ├── installer.py
│   ├── forms.py
│   └── templates/
├── wsjtx/
│   ├── __init__.py
│   └── ...
└── winlink//
    ├── __init__.py
    └── .../
```
#### Step 3 — Restart the Application
##### Standard installation
    source venv/bin/activate
    python app.py
##### Or if running as a service
    sudo systemctl restart ham-radio-app
##### Or Docker
    docker compose restart app
#### Step 4 — First Run (Automatic Dependency Installation)
When the application starts, each plugin checks for its required dependencies.\ 
If they are not installed, the plugin will:
    - Display an Install button on its page
    - You can also click Install from the plugin page to trigger installation
    - Installation progress is shown in real time
    - Some plugins (like SatDump) may take 15–30 minutes to build from source
    Note: Installation requires an internet connection. Some plugins require sudo for system package installation.

#### Step 5 — Configure the Plugin
After installation:
- [ ] Navigate to the plugin page via the Dashboard or Plugins menu
- [ ] Click Settings
- [ ] Configure the plugin for your station
- [ ] Save settings and start the plugin
##### Plugin-Specific Requirements
###### FLdigi
- [ ] FLdigi must have XML-RPC enabled
- [ ] In FLdigi: Configure → XML-RPC
- [ ] Set Host: localhost, Port: 7362
- [ ] Enable: "XML-RPC server"

##### WSJT-X
- [ ] WSJT-X must have UDP enabled
- [ ] In WSJT-X: File → Settings → Reporting
- [ ] Set UDP Server: localhost
- [ ] Set Port: 2237
- [ ] Enable: "Accept UDP requests"

##### Winlink (Pat)
- [ ] Pat is installed automatically
- [ ] Configure callsign in plugin settings
- [ ] Supports: Telnet, AX.25, VARA HF, VARA FM, ARDOP

##### QSSTV
- [ ] QSSTV requires a display (X11)
- [ ] For headless servers, 
###### use Xvfb:
    sudo apt-get install xvfb
    Xvfb :1 -screen 0 1024x768x24 &
    export DISPLAY=:1
    Set Display=:1 in QSSTV plugin settings

##### SatDump
 - [ ] SatDump build requires ~4 GB disk space
 - [ ] Build time: 15-30 minutes on Raspberry Pi 4
###### Recommended antennas:
 - [ ] VHF (137 MHz): V-dipole or QFH for NOAA/METEOR
 - [ ] L-Band (1.7 GHz): Patch antenna for GOES/Meteosat

#### OpenWebRX
 - [ ] OpenWebRX is installed via Docker (recommended)
 - [ ] Requires Docker to be installed
 - [ ] Exposes web interface on port 8073
</details>

#### Canadian Callsign Database
The application can validate and display information about Canadian amateur radio operators using the official ISED (Innovation, Science and Economic Development Canada) database.
<details>
What It Does:\
    - Validates callsigns during registration against the official licence database\
    - Displays your name and qualifications on the dashboard\
    - Quick lookup of any Canadian callsign from the dashboard

##### Downloading the Database
 - [ ] Log in to the application
 - [ ] On the Dashboard, click the database icon 🗄️ in the Operator card
 - [ ] Click Download / Update Database
 - [ ] Wait for the download to complete (~1–2 minutes)

##### The database contains:
80,000+ licensed Canadian operators
    - Full names and qualifications
    - City, province, and postal code
    - Qualification levels (Basic, Advanced, Morse, etc.)
    
##### Updating the Database
The ISED database is updated periodically. We recommend updating every 90 days.
The dashboard will show a warning when the database is out of date.

##### Enabling Callsign Validation on Registration
To require valid Canadian callsigns during user registration:

###### In .env file
    VALIDATE_CALLSIGNS=true
    Note: This only validates Canadian callsigns (VE, VA, VY, VO prefixes). International callsigns pass format validation only.
</details>

#### Accessing the Application
##### Local Access
    https://localhost:5000

##### Over WiFi Hotspot
###### Find server IP
    ip addr show wlan0
###### Connect client device to hotspot
##### Browse to:
    https://192.168.x.x:5000

#### SSL Certificate Warning
The application uses a self-signed SSL certificate by default. Your browser will show a security warning on first access. This is normal and expected for local network use.

##### To accept the certificate:
Chrome/Edge: Click "Advanced" → "Proceed to [IP] (unsafe)"\
Firefox: Click "Advanced" → "Accept the Risk and Continue"\
Safari: Click "Show Details" → "visit this website"\

### First Time Setup
 - [ ] Browse to https://localhost:5000
 - [ ] Register a new account with your callsign
 - [ ] Log in with your credentials

#### On the Dashboard, verify your callsign is shown
 - [ ] Click the database icon to download the Canadian callsign database
 - [ ] Navigate to Settings for any plugin you want to use
 - [ ] Check the Logbook to start logging contacts

## Troubleshooting
<details>
    
### Application Will Not Start
#### Check Python version (needs 3.8+)
    python3 --version
#### Check for missing packages
    pip install -r requirements.txt

#### Check logs
    python app.py 2>&1 | head -50

### Cannot Connect to Application
#### Check if application is running
    ps aux | grep "python app.py"
#### Check port is listening
    ss -tlnp | grep 5000
#### Check firewall
    sudo ufw status
    sudo ufw allow 5000/tcp
### Device Not Detected
#### Check USB devices
    lsusb
#### Check serial ports
    ls -l /dev/ttyUSB*
#### Check user permissions
    groups $USER
    -[ ] Should include 'dialout'
        - Add to dialout group if missing
        - sudo usermod -a -G dialout $USER
    -[ ] Log out and back in

### RTL-SDR Not Working
#### Check RTL-SDR is detected
    rtl_test -t

#### Add udev rules if needed
    sudo tee /etc/udev/rules.d/rtl-sdr.rules << 'EOF'
    SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", GROUP="plugdev", MODE="0664"
    SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", GROUP="plugdev", MODE="0664"
    EOF
    sudo udevadm control --reload-rules
    sudo usermod -a -G plugdev $USER

### Database Errors

#### Reset the database (WARNING: deletes all data)
    rm data/db/ham_radio.db
    python app.py  # Tables will be recreated

#### Check database integrity
    sqlite3 data/db/ham_radio.db ".tables"

### Plugin Not Appearing on Dashboard
#### Check plugin directory structure
    ls -la plugins/implementations/
#### Run the diagnostic script
    python check_plugins.py
#### Check application logs for import errors
    python app.py 2>&1 | grep -i "plugin\|error"

### Docker Container Issues
#### Check container logs
    docker compose logs app
#### Check container is running
    docker compose ps
#### Access container for debugging
    docker compose exec app bash
#### Fix permissions on data directory
    sudo chown -R 1000:1000 data/

### SSL Certificate Issues
#### Regenerate SSL certificates
    rm data/certs/*.pem
    python app.py  # New certificates will be generated

#### Disable SSL temporarily for testing
#### In .env:
    USE_SSL=false
</details>

## Project Structure
<details>
```scss
ham-radio-app/
├── app.py                    # Application entry point
├── config.py                 # Configuration management
├── requirements.txt          # Python dependencies
├── setup.sh                  # Setup script
├── check_plugins.py          # Plugin diagnostic tool
├── .env.example              # Example environment file
├── Dockerfile                # Docker build file
├── docker-compose.yml        # Docker Compose configuration
├── ham-radio-app.service     # Systemd service file
│
├── auth/                     # Authentication module
│   ├── forms.py              # Login/registration forms
│   └── routes.py             # Auth routes
│
├── callsign_db/              # Canadian callsign database
│   ├── database.py           # Database interface
│   ├── downloader.py         # ISED download manager
│   ├── models.py             # SQLAlchemy models
│   └── validator.py          # Callsign validation
│
├── dashboard/                # Dashboard module
│   └── routes.py             # Dashboard routes and APIs
│
├── logbook/                  # Contact logging module
│   ├── export.py             # ADIF/CSV/JSON export
│   ├── forms.py              # Log entry forms
│   └── routes.py             # Logbook routes
│
├── models/                   # Database models
│   ├── logbook.py            # Contact log model
│   └── user.py               # User model
│
├── devices/                  # Hardware device interfaces
│   ├── base.py               # Base device class + mocks
│   ├── gps.py                # GPS (NMEA serial)
│   ├── radio.py              # Radio (Hamlib)
│   └── sdr.py                # RTL-SDR
│
├── plugins/                  # Plugin system
│   ├── base.py               # BasePlugin abstract class
│   ├── loader.py             # Plugin discovery/loading
│   ├── routes.py             # Plugin management routes
│   └── implementations/      # Plugin packages
│       ├── fldigi/           # FLdigi digital modes
│       ├── wsjtx/            # WSJT-X weak signal modes
│       ├── winlink/          # Winlink email over radio
│       ├── graywolf/         # GrayWolf Winlink gateway
│       ├── openwebrx/        # OpenWebRX SDR receiver
│       ├── qsstv/            # QSSTV slow scan TV
│       └── satdump/          # SatDump satellite receiver
│
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Base template + navigation
│   ├── auth/                 # Login/register pages
│   ├── dashboard/            # Dashboard page
│   ├── errors/               # 404/500 error pages
│   ├── logbook/              # Logbook pages
│   └── plugins/              # Generic plugin templates
│
├── static/                   # Static web assets
│   ├── css/style.css         # Custom styles
│   └── js/app.js             # Custom JavaScript
│
└── data/                     # Persistent data (gitignored)
    ├── db/                   # SQLite databases
    ├── certs/                # SSL certificates
    ├── backups/              # Database backups
    └── callsigns/            # Callsign database files
```
</details>

## Contributing
Contributions are welcome! Here is how to get started:

## Reporting Bugs
    Check the Issues page first\
### Open a new issue with:
    Your OS and Python version
    Steps to reproduce
    Expected vs actual behaviour
    Relevant log output
### Submitting Changes
    Fork the repository
    Create a feature branch: git checkout -b feature/my-feature
    Make your changes with clear commit messages
    Test with python check_plugins.py
    Submit a pull request
### Writing a New Plugin
    Copy an existing simple plugin as a template (e.g., winlink/)
    Inherit from BasePlugin in plugins/base.py
    Implement the required methods:
    initialize() — set up plugin resources
    shutdown() — clean up on exit
    get_blueprint() — return your Flask blueprint
    Add an installer.py for dependency management
    Add templates to templates/ inside your plugin directory
    Test discovery with python check_plugins.py
## Acknowledgements
This application integrates with many excellent open-source projects:\
\
Flask — Web framework\
Hamlib — Radio control library\
FLdigi — Digital modes modem\
WSJT-X — Weak signal modes\
Pat Winlink — Winlink client\
OpenWebRX — Web SDR\
QSSTV — SSTV software\
SatDump — Satellite processing\
GrayWolf — Winlink gateway\
RTL-SDR — SDR hardware/software\
ISED Canada — Amateur radio database\
## License
This project is licensed under the MIT License.\
See the LICENSE file for details.\

MIT License — Free to use, modify, and distribute.\
Attribution appreciated but not required.\

<div align="center">
73\
- Ham Radio App Team

</div>
