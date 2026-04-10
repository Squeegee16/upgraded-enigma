"""
GPS abstraction layer.
Allows mock or real GPS via config.
"""

import random

def get_location():
    # Mock GPS fallback
    return {
        "lat": 45.42 + random.uniform(-0.1, 0.1),
        "lon": -75.69 + random.uniform(-0.1, 0.1),
        "grid": "FN25"
    }