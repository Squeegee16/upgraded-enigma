/**
 * Ham Radio App - Main JavaScript
 */

// Update UTC clock every second
function updateClock() {
    const now = new Date();
    const utcTime = now.toISOString().slice(11, 19);
    $('#time-display').text(utcTime + ' UTC');
}

// Initialize clock update
$(document).ready(function() {
    updateClock();
    setInterval(updateClock, 1000);
    
    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        $('.alert').fadeOut('slow');
    }, 5000);
    
    // Confirm delete actions
    $('form[data-confirm]').on('submit', function(e) {
        if (!confirm($(this).data('confirm'))) {
            e.preventDefault();
            return false;
        }
    });
    
    // Enable tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// AJAX error handler
$(document).ajaxError(function(event, jqxhr, settings, thrownError) {
    console.error('AJAX Error:', thrownError);
    
    // Show error message if not handled
    if (!settings.suppressErrors) {
        alert('An error occurred. Please try again.');
    }
});

// Utility: Format frequency
function formatFrequency(freqMhz) {
    return parseFloat(freqMhz).toFixed(3) + ' MHz';
}

// Utility: Format date/time
function formatDateTime(dateString) {
    const date = new Date(dateString);
    return date.toISOString().slice(0, 19).replace('T', ' ') + ' UTC';
}

// Utility: Validate callsign format
function validateCallsign(callsign) {
    const regex = /^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z]$/i;
    return regex.test(callsign);
}