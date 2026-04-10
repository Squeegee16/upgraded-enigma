# upgraded-enigma
Project structure

hamradio_app/
│
├── app.py
├── config.py
├── extensions.py
├── models.py
├── gps_service.py
├── plugin_loader.py
│
├── auth/
│   ├── routes.py
│   ├── forms.py
│
├── dashboard/
│   └── routes.py
│
├── logbook/
│   ├── routes.py
│   ├── exporter.py
│
├── plugins/
│   ├── __init__.py
│   ├── base_plugin.py
│   └── example_plugin/
│       └── plugin.py
│
├── templates/
├── static/
└── README.md

#WiFi Hotspot
sudo apt install hostapd dnsmasq

#Setup
sudo apt install python3 python3-venv
python3 -m venv venv
source venv/bin/activate
pip install flask flask-login flask-bcrypt flask-wtf flask-sqlalchemy

#Generate self-signed cert:
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

#run
python app.py

#Access from laptop/tablet:
https://<hotspot-ip>
