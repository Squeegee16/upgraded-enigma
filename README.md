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
