"""
Logbook Routes
==============
Routes for viewing, adding, and exporting contact logs.
"""
import logging
# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, make_response
from flask_login import login_required, current_user
from models import db
from models.logbook import ContactLog
from logbook.forms import ContactLogForm
from logbook.export import get_export_function
from datetime import datetime
from io import BytesIO
from sqlalchemy import func

logbook_bp = Blueprint('logbook', __name__, url_prefix='/logbook')

@logbook_bp.route('/')
@login_required
def index():
    """
    Display user's contact log.
    
    Supports filtering and pagination.
    """
    try:
        # Get filter parameters
        callsign_filter = request.args.get('callsign', '').strip()
        mode_filter = request.args.get('mode', '').strip()
        band_filter = request.args.get('band', '').strip()
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        # Build query
        query = ContactLog.query.filter_by(operator_id=current_user.id)
        
        # Apply filters
        if callsign_filter:
            query = query.filter(ContactLog.contact_callsign.ilike(f'%{callsign_filter}%'))
        
        if mode_filter:
            query = query.filter_by(mode=mode_filter)
        
        if band_filter:
            query = query.filter_by(band=band_filter)
        
        # Order by timestamp descending
        query = query.order_by(ContactLog.timestamp.desc())
        
        # Paginate with error handling for different SQLAlchemy versions
        try:
            # Try newer SQLAlchemy 3.x syntax
            pagination = db.paginate(
                query,
                page=page,
                per_page=per_page,
                error_out=False
            )
            contacts = pagination.items
        except AttributeError:
            # Fall back to older SQLAlchemy 2.x syntax
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            contacts = pagination.items
        
        # Get unique modes and bands for filters with error handling
        try:
            modes_result = db.session.query(ContactLog.mode).filter_by(
                operator_id=current_user.id
            ).distinct().all()
            modes = sorted([m[0] for m in modes_result if m[0]])
            
            bands_result = db.session.query(ContactLog.band).filter_by(
                operator_id=current_user.id
            ).filter(ContactLog.band.isnot(None)).distinct().all()
            bands = sorted([b[0] for b in bands_result if b[0]])
        except Exception as e:
            print(f"Error getting filter options: {e}")
            modes = []
            bands = []
        
        return render_template(
            'logbook/index.html',
            contacts=contacts,
            pagination=pagination,
            modes=modes,
            bands=bands,
            filters={
                'callsign': callsign_filter,
                'mode': mode_filter,
                'band': band_filter
            }
        )
    except Exception as e:
        print(f"Error in logbook index: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading logbook: {str(e)}', 'danger')
        return redirect(url_for('dashboard.index'))

@logbook_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_contact():
    """
    Add a new contact to the logbook.
    """
    form = ContactLogForm()
    
    if form.validate_on_submit():
        try:
            contact = ContactLog(
                operator_id=current_user.id,
                contact_callsign=form.contact_callsign.data.upper(),
                mode=form.mode.data,
                band=form.band.data if form.band.data else None,
                frequency=form.frequency.data,
                grid=form.grid.data.upper() if form.grid.data else None,
                timestamp=form.timestamp.data,
                signal_report_sent=form.signal_report_sent.data,
                signal_report_rcvd=form.signal_report_rcvd.data,
                notes=form.notes.data
            )
            
            db.session.add(contact)
            db.session.commit()
            flash(f'Contact with {contact.contact_callsign} logged successfully!', 'success')
            return redirect(url_for('logbook.index'))
        except Exception as e:
            db.session.rollback()
            print(f"Error adding contact: {e}")
            import traceback
            traceback.print_exc()
            flash(f'Error logging contact: {str(e)}', 'danger')
    
    return render_template('logbook/add_contact.html', form=form)

@logbook_bp.route('/edit/<int:contact_id>', methods=['GET', 'POST'])
@login_required
def edit_contact(contact_id):
    """
    Edit an existing contact.
    """
    try:
        contact = ContactLog.query.filter_by(
            id=contact_id,
            operator_id=current_user.id
        ).first_or_404()
        
        form = ContactLogForm(obj=contact)
        
        if form.validate_on_submit():
            try:
                contact.contact_callsign = form.contact_callsign.data.upper()
                contact.mode = form.mode.data
                contact.band = form.band.data if form.band.data else None
                contact.frequency = form.frequency.data
                contact.grid = form.grid.data.upper() if form.grid.data else None
                contact.timestamp = form.timestamp.data
                contact.signal_report_sent = form.signal_report_sent.data
                contact.signal_report_rcvd = form.signal_report_rcvd.data
                contact.notes = form.notes.data
                
                db.session.commit()
                flash('Contact updated successfully!', 'success')
                return redirect(url_for('logbook.index'))
            except Exception as e:
                db.session.rollback()
                print(f"Error updating contact: {e}")
                flash(f'Error updating contact: {str(e)}', 'danger')
        
        return render_template('logbook/edit_contact.html', form=form, contact=contact)
    except Exception as e:
        print(f"Error in edit_contact: {e}")
        flash('Contact not found or error occurred', 'danger')
        return redirect(url_for('logbook.index'))

@logbook_bp.route('/delete/<int:contact_id>', methods=['POST'])
@login_required
def delete_contact(contact_id):
    """
    Delete a contact from the logbook.
    """
    try:
        contact = ContactLog.query.filter_by(
            id=contact_id,
            operator_id=current_user.id
        ).first_or_404()
        
        db.session.delete(contact)
        db.session.commit()
        flash('Contact deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting contact: {e}")
        flash(f'Error deleting contact: {str(e)}', 'danger')
    
    return redirect(url_for('logbook.index'))

@logbook_bp.route('/export/<format_type>')
@login_required
def export(format_type):
    """
    Export logbook in specified format.
    
    Args:
        format_type: Export format (csv, json, adif)
    """
    try:
        # Validate format
        valid_formats = ['csv', 'json', 'adif']
        if format_type not in valid_formats:
            flash('Invalid export format', 'danger')
            return redirect(url_for('logbook.index'))
        
        # Get filters from request
        callsign_filter = request.args.get('callsign', '').strip()
        mode_filter = request.args.get('mode', '').strip()
        band_filter = request.args.get('band', '').strip()
        
        # Build query
        query = ContactLog.query.filter_by(operator_id=current_user.id)
        
        # Apply filters
        if callsign_filter:
            query = query.filter(ContactLog.contact_callsign.ilike(f'%{callsign_filter}%'))
        
        if mode_filter:
            query = query.filter_by(mode=mode_filter)
        
        if band_filter:
            query = query.filter_by(band=band_filter)
        
        # Order by timestamp
        query = query.order_by(ContactLog.timestamp.desc())
        contacts = query.all()
        
        # Check if there are contacts to export
        if not contacts:
            flash('No contacts found to export', 'warning')
            return redirect(url_for('logbook.index'))
        
        # Get export function
        export_func = get_export_function(format_type)
        
        if not export_func:
            flash('Export function not available', 'danger')
            return redirect(url_for('logbook.index'))
        
        # Generate export data
        export_data = export_func(contacts)
        
        # Determine MIME type and extension
        mime_types = {
            'csv': 'text/csv',
            'json': 'application/json',
            'adif': 'text/plain'
        }
        
        extensions = {
            'csv': 'csv',
            'json': 'json',
            'adif': 'adi'
        }
        
        # Create filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f'logbook_{current_user.callsign}_{timestamp}.{extensions[format_type]}'
        
        # Create response
        response = make_response(export_data)
        response.headers['Content-Type'] = mime_types[format_type]
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
    except Exception as e:
        print(f"Error exporting logbook: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error exporting logbook: {str(e)}', 'danger')
        return redirect(url_for('logbook.index'))

@logbook_bp.route('/stats')
@login_required
def statistics():
    """
    Display logbook statistics.
    """
    try:
        # Total contacts
        total_contacts = ContactLog.query.filter_by(operator_id=current_user.id).count()
        
        # Contacts by mode
        mode_stats = db.session.query(
            ContactLog.mode,
            func.count(ContactLog.id)
        ).filter_by(operator_id=current_user.id).group_by(ContactLog.mode).all()
        
        # Contacts by band
        band_stats = db.session.query(
            ContactLog.band,
            func.count(ContactLog.id)
        ).filter_by(
            operator_id=current_user.id
        ).filter(
            ContactLog.band.isnot(None)
        ).group_by(ContactLog.band).all()
        
        # Unique callsigns contacted
        unique_callsigns = db.session.query(
            func.count(func.distinct(ContactLog.contact_callsign))
        ).filter_by(operator_id=current_user.id).scalar()
        
        # Recent activity (last 30 days)
        from datetime import timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_contacts = ContactLog.query.filter(
            ContactLog.operator_id == current_user.id,
            ContactLog.timestamp >= thirty_days_ago
        ).count()
        
        return render_template(
            'logbook/statistics.html',
            total_contacts=total_contacts,
            mode_stats=mode_stats,
            band_stats=band_stats,
            unique_callsigns=unique_callsigns,
            recent_contacts=recent_contacts
        )
    except Exception as e:
        print(f"Error loading statistics: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading statistics: {str(e)}', 'danger')
        return redirect(url_for('dashboard.index'))
