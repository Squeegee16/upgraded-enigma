#!/usr/bin/env python
"""Add test data to the database."""

from app import create_app
from models import db
from models.user import User
from models.logbook import ContactLog
from datetime import datetime, timedelta
import random

def add_test_data():
    app = create_app()
    
    with app.app_context():
        # Check if user exists
        user = User.query.filter_by(callsign='W1TEST').first()
        
        if not user:
            print("Creating test user...")
            user = User(callsign='W1TEST')
            user.set_password('Test123!')
            db.session.add(user)
            db.session.commit()
            print(f"Created user: {user.callsign}")
        
        # Add some test contacts
        print("Adding test contacts...")
        
        modes = ['SSB', 'CW', 'FT8', 'FM']
        bands = ['20m', '40m', '10m', '2m']
        
        for i in range(10):
            contact = ContactLog(
                operator_id=user.id,
                contact_callsign=f'K{random.randint(1,9)}TEST{chr(65+random.randint(0,25))}',
                mode=random.choice(modes),
                band=random.choice(bands),
                frequency=14.074 + random.uniform(-0.5, 0.5),
                grid=f'FN{random.randint(10,49)}',
                timestamp=datetime.utcnow() - timedelta(days=random.randint(0, 30)),
                signal_report_sent='59',
                signal_report_rcvd='59',
                notes=f'Test contact {i+1}'
            )
            db.session.add(contact)
        
        db.session.commit()
        print(f"Added 10 test contacts for {user.callsign}")
        
        # Verify
        count = ContactLog.query.filter_by(operator_id=user.id).count()
        print(f"Total contacts in database: {count}")

if __name__ == '__main__':
    add_test_data()
