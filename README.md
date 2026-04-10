ham_radio_app/
├── app.py                      # Main application entry point
├── config.py                   # Configuration management
├── requirements.txt            # Python dependencies
├── README.md                   # Setup and usage instructions
├── models/
│   ├── __init__.py
│   ├── user.py                # User model
│   └── logbook.py             # Contact log model
├── auth/
│   ├── __init__.py
│   ├── routes.py              # Authentication routes
│   └── forms.py               # Authentication forms
├── dashboard/
│   ├── __init__.py
│   └── routes.py              # Dashboard routes
├── logbook/
│   ├── __init__.py
│   ├── routes.py              # Logbook routes
│   ├── forms.py               # Logbook forms
│   └── export.py              # Export functionality
├── plugins/
│   ├── __init__.py
│   ├── base.py                # Base plugin class
│   ├── loader.py              # Plugin discovery and loading
│   ├── routes.py              # Plugin routes
│   └── implementations/
│       ├── __init__.py
│       ├── sdr_monitor.py     # SDR Monitor plugin
│       ├── fldigi.py          # FLdigi plugin (stub)
│       └── winlink.py         # Winlink plugin (stub)
├── devices/
│   ├── __init__.py
│   ├── base.py                # Base device interface
│   ├── gps.py                 # GPS device interface
│   ├── radio.py               # Radio control via Hamlib
│   └── sdr.py                 # RTL-SDR interface
├── templates/
│   ├── base.html              # Base template with navigation
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── dashboard/
│   │   └── index.html
│   ├── logbook/
│   │   ├── index.html
│   │   └── add_contact.html
│   └── plugins/
│       └── plugin_page.html
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
└── data/
    ├── callsigns.txt          # Valid callsign list
    └── certs/                 # SSL certificates
        ├── cert.pem
        └── key.pem

        # Ham Radio Operator Web Application

A comprehensive web-based application for ham radio operators, featuring a modular plugin architecture, device integration, and contact logging.

## Features

- **User Authentication**: Secure registration and login with callsign validation
- **Dashboard**: Real-time display of GPS location, time, and device status
- **Contact Logging**: Unified logbook with support for all standard fields
- **Export Options**: Export logs in ADIF, CSV, and JSON formats
- **Plugin System**: Modular architecture for integrating external programs
- **Device Integration**: Support for GPS, Hamlib-compatible radios, and RTL-SDR
- **Responsive UI**: Works on laptops and tablets
- **SSL Support**: HTTPS with self-signed certificates for local network security

## Requirements

### System Requirements

- Linux-based operating system (tested on Ubuntu 20.04+)
- Python 3.8 or higher
- WiFi adapter capable of hosting a hotspot

### Python Dependencies

```bash
Flask==3.0.0
Flask-Login==0.6.3
Flask-WTF==1.2.1
Flask-SQLAlchemy==3.1.1
WTForms==3.1.1
bcrypt==4.1.2
pyserial==3.5
adif-io==0.1.2
requests==2.31.0

# For GPS support
pip install pynmea2

# For SSL certificate generation
pip install pyopenssl

# For SDR support (if using Python library instead of rtl_sdr command)
pip install pyrtlsdr numpy

# Hamlib: For radio control
sudo apt-get install hamlib-utils

#RTL-SDR: For SDR functionality
sudo apt-get install rtl-sdr

#FLdigi: For digital modes
sudo apt-get install fldigi

#SDR Monitor: For spectrum monitoring 
# Follow installation instructions at:
# https://github.com/shajen/sdr-monitor

#Installation
cd /opt
sudo git clone <repository-url> ham_radio_app
cd ham_radio_app
#Create Virtual Environment
python3 -m venv venv
source venv/bin/activate
#Install Dependencies
pip install -r requirements.txt
#Create Required Directories
mkdir -p data/certs
mkdir -p plugins/implementations

#Configure the Application - config.py
# For production use
export FLASK_ENV=production
export SECRET_KEY='your-secret-key-here'

# Device configuration
export USE_MOCK_DEVICES=False  # Set to True for testing without hardware
export GPS_SERIAL_PORT=/dev/ttyUSB0
export RADIO_PORT=/dev/ttyUSB1
export RADIO_MODEL=1035  # Yaesu FT-891

# SSL configuration
export USE_SSL=True
VALIDATE_CALLSIGNS = True

#Create Callsign Database
#data/callsigns.txt:
# One callsign per line
W1ABC
K2XYZ
N3QRS

#dev mode
source venv/bin/activate
python app.py

#prod
source venv/bin/activate
export FLASK_ENV=production
export USE_MOCK_DEVICES=False
python app.py



#Setup WiFi Hotspot
# Example using nmcli
sudo nmcli dev wifi hotspot ssid HamRadioApp password "yourpassword"
ip addr show wlan0

Connect from Client Device:

Connect to the WiFi hotspot
Open browser and navigate to: https://<server-ip>:5000
Accept the self-signed certificate warning
First Time Setup

Navigate to the application URL
Click "Register" to create an account
Enter your callsign and create a strong password
Log in with your credentials
Explore the dashboard and available plugins

#Key configuration options:
# Database
SQLALCHEMY_DATABASE_URI = 'sqlite:///ham_radio.db'

# Server
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 5000

# Devices
USE_MOCK_DEVICES = True  # Set False for real hardware
GPS_SERIAL_PORT = '/dev/ttyUSB0'
RADIO_MODEL = 1035  # Hamlib model number
RADIO_PORT = '/dev/ttyUSB1'

# SSL
USE_SSL = True
SSL_CERT = 'data/certs/cert.pem'
SSL_KEY = 'data/certs/key.pem'

#Creating a New Plugin
#Create a new file in plugins/implementations/:

# from plugins.base import BasePlugin
# from flask import Blueprint, render_template
# from flask_login import login_required

# class MyPlugin(BasePlugin):
#     name = "My Plugin"
#     description = "Description of my plugin"
#     version = "1.0.0"
#     author = "Your Name"
    
#     def initialize(self):
#         # Initialize plugin resources
#         return True
    
#     def shutdown(self):
#         # Cleanup resources
#         pass
    
#     def get_blueprint(self):
#         bp = Blueprint('My Plugin', __name__, url_prefix='/plugin/myplugin')
        
#         @bp.route('/')
#         @login_required
#         def index():
#             return render_template('plugins/myplugin.html', plugin=self)
        
#         return bp

Create template in templates/plugins/myplugin.html

Accessing Devices from Plugins
# In your plugin
def some_method(self):
    gps = self.get_device('gps')
    if gps and gps.is_connected():
        position = gps.get_position()
    
    radio = self.get_device('radio')
    if radio:
        frequency = radio.get_frequency()

#Logging Contacts from Plugins
contact_data = {
    'callsign': 'W1ABC',
    'mode': 'FT8',
    'band': '20m',
    'frequency': 14.074,
    'grid': 'FN42',
    'rst_sent': '-10',
    'rst_rcvd': '-15',
    'notes': 'Nice QSO'
}

success = self.log_contact(contact_data)


Troubleshooting:
# Reset database (WARNING: deletes all data)
rm ham_radio.db
python app.py

#Check device permissions:
sudo usermod -a -G dialout $USER
# Logout and login again

#Verify device paths:
ls -l /dev/ttyUSB*

Test devices independently:
# GPS
cat /dev/ttyUSB0

# Radio (Hamlib)
rigctl -m 1035 -r /dev/ttyUSB1 f

# RTL-SDR
rtl_test

#SSL Certificate Issues
#Regenerate certificates:
rm data/certs/*
python app.py

#Or disable SSL for testing:
export USE_SSL=False
python app.py

#Plugin Not Loading
Check plugin file is in plugins/implementations/
Verify plugin class inherits from BasePlugin
Check application logs for errors
Ensure __init__.py exists in plugin directory

#Security Considerations
#For Production Use
#Change the SECRET_KEY:
export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')

Use Strong Passwords: Enforce password requirements
Enable SSL: Always use HTTPS, even on local networks

#Firewall Configuration:
sudo ufw allow 5000/tcp
sudo ufw enable

Contributing
Contributions are welcome! Please:

Fork the repository
Create a feature branch
Make your changes
Submit a pull request

Support
For issues and questions:

Check the troubleshooting section
Review application logs
Submit an issue on GitHub
Acknowledgments
Hamlib project for radio control
RTL-SDR project for SDR support
FLdigi for digital modes
SDR Monitor project (https://github.com/shajen/sdr-monitor)
Ham radio community for inspiration and support
