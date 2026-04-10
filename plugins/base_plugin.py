"""
Plugin interface every plugin must implement.
"""

class BasePlugin:
    name = "Base Plugin"
    route = "/plugin"

    def get_blueprint(self):
        raise NotImplementedError

    def get_device(self):
        raise NotImplementedError