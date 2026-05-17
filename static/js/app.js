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
/* ============================================================
   Device Navigation Warning
   ============================================================
   Warns the user before navigating away from a plugin page
   that has active devices claimed.
   ============================================================ */

/**
 * Check if the current plugin has any devices claimed
 * and warn before navigation.
 *
 * Call this from each plugin's page load to register
 * the navigation guard.
 *
 * @param {string} pluginName - Name of current plugin
 * @param {string[]} devices - Devices this plugin uses
 */
function registerDeviceNavigationGuard(pluginName, devices) {
    if (!devices || devices.length === 0) return;

    // Warn before page unload (browser navigation)
    window.addEventListener('beforeunload', function(e) {
        const hasActiveDevices = checkPluginHasDevices(
            pluginName
        );
        if (hasActiveDevices) {
            const msg = (
                `${pluginName} is still using devices. ` +
                `Navigate away to release them.`
            );
            e.returnValue = msg;
            return msg;
        }
    });

    // Intercept navbar links to dashboard
    document.querySelectorAll(
        'a[href*="/dashboard"]'
    ).forEach(function(link) {
        link.addEventListener('click', function(e) {
            const hasActive = checkPluginHasDevices(
                pluginName
            );
            if (hasActive) {
                e.preventDefault();
                showDeviceWarningModal(
                    pluginName,
                    devices,
                    link.href
                );
            }
        });
    });

    // Intercept plugin switch links
    document.querySelectorAll(
        'a[href*="/plugin/"]'
    ).forEach(function(link) {
        // Don't intercept links to this plugin
        if (link.href.includes(
            '/plugin/' + pluginName.toLowerCase()
        )) return;

        link.addEventListener('click', function(e) {
            const hasActive = checkPluginHasDevices(
                pluginName
            );
            if (hasActive) {
                e.preventDefault();
                showDeviceWarningModal(
                    pluginName,
                    devices,
                    link.href
                );
            }
        });
    });
}

/**
 * Check (synchronously from cache) if plugin has devices.
 * Uses the last known device status from the API.
 */
let _lastDeviceStatus = {};

function checkPluginHasDevices(pluginName) {
    return Object.values(_lastDeviceStatus).some(
        function(dev) {
            return dev.owner === pluginName;
        }
    );
}

/**
 * Show a modal warning the user about active devices
 * before navigating away.
 */
function showDeviceWarningModal(pluginName, devices,
                                 targetUrl) {
    // Get or create the warning modal
    let modal = document.getElementById(
        'deviceWarningModal'
    );

    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'deviceWarningModal';
        modal.className = 'modal fade';
        modal.setAttribute('tabindex', '-1');
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header
                                bg-warning text-dark">
                        <h5 class="modal-title">
                            <i class="fas fa-exclamation-triangle
                                      me-2"></i>
                            Device In Use
                        </h5>
                        <button type="button"
                                class="btn-close"
                                data-bs-dismiss="modal">
                        </button>
                    </div>
                    <div class="modal-body"
                         id="deviceWarningBody">
                    </div>
                    <div class="modal-footer">
                        <button type="button"
                                class="btn btn-secondary"
                                data-bs-dismiss="modal">
                            Stay on ${pluginName}
                        </button>
                        <button type="button"
                                class="btn btn-warning"
                                id="deviceWarningConfirm">
                            <i class="fas fa-sign-out-alt
                                      me-1"></i>
                            Leave and Release Devices
                        </button>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(modal);
    }

    // Build warning message
    const ownedDevices = Object.entries(
        _lastDeviceStatus
    ).filter(
        ([k, v]) => v.owner === pluginName
    ).map(([k]) => k.toUpperCase());

    document.getElementById(
        'deviceWarningBody'
    ).innerHTML = `
        <p>
            The <strong>${pluginName}</strong> plugin
            currently has the following devices active:
        </p>
        <ul class="mb-3">
            ${ownedDevices.map(d =>
                `<li>
                    <strong>${d}</strong>
                </li>`
            ).join('')}
        </ul>
        <p class="mb-0">
            If you navigate away, these devices will be
            released and ${pluginName} will stop using them.
        </p>
        <div class="alert alert-info small mt-2 mb-0">
            <i class="fas fa-info-circle me-1"></i>
            You can return to <strong>${pluginName}</strong>
            later and reclaim the devices.
        </div>`;

    // Set confirm button action
    const confirmBtn = document.getElementById(
        'deviceWarningConfirm'
    );
    confirmBtn.onclick = function() {
        // Release devices via API then navigate
        releasePluginDevices(pluginName, function() {
            window.location.href = targetUrl;
        });
    };

    new bootstrap.Modal(modal).show();
}

/**
 * Release all devices for a plugin via the API.
 *
 * @param {string} pluginName - Plugin releasing devices
 * @param {function} callback - Called after release
 */
function releasePluginDevices(pluginName, callback) {
    $.ajax({
        url: '/plugin/release_devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({plugin: pluginName}),
        complete: function() {
            // Always call callback even if API fails
            if (callback) callback();
        }
    });
}

// Poll device status every 15 seconds to keep cache fresh
setInterval(function() {
    $.ajax({
        url: '/dashboard/api/devices',
        method: 'GET',
        timeout: 5000,
        success: function(data) {
            if (data && typeof data === 'object') {
                _lastDeviceStatus = data;
            }
        }
    });
}, 15000);

// Load once on page load
$(document).ready(function() {
    $.ajax({
        url: '/dashboard/api/devices',
        method: 'GET',
        timeout: 5000,
        success: function(data) {
            if (data && typeof data === 'object') {
                _lastDeviceStatus = data;
            }
        }
    });
});
