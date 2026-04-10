"""
Plugin Routes
=============
Common routes for plugin management and display.
"""

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

plugins_bp = Blueprint('plugins', __name__, url_prefix='/plugins')

@plugins_bp.route('/')
@login_required
def index():
    """
    Display list of all available plugins.
    """
    from flask import current_app
    plugin_loader = current_app.extensions.get('plugin_loader')
    
    if plugin_loader:
        plugins = plugin_loader.get_all_plugins()
    else:
        plugins = {}
    
    return render_template('plugins/index.html', plugins=plugins)

@plugins_bp.route('/<plugin_name>')
@login_required
def plugin_page(plugin_name):
    """
    Display a specific plugin's page.
    
    This route redirects to the plugin's own blueprint routes.
    """
    from flask import current_app
    plugin_loader = current_app.extensions.get('plugin_loader')
    
    if plugin_loader:
        plugin = plugin_loader.get_plugin(plugin_name)
        if plugin:
            # Redirect to plugin's main route
            return redirect(url_for(f'{plugin_name}.index'))
    
    flash(f'Plugin "{plugin_name}" not found', 'danger')
    return redirect(url_for('plugins.index'))