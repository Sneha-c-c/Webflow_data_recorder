from PyQt5.QtCore import QObject, pyqtSignal

# Create a signal class for thread communication
class WorkerSignals(QObject):
    # Basic signals
    finished = pyqtSignal()
    error = pyqtSignal(str, str)
    success = pyqtSignal(str)
    warning = pyqtSignal(str, str)
    update_status = pyqtSignal(str)
    
    # Additional signals for specific events
    page_captured = pyqtSignal(str, str)  # URL, title
    alert_captured = pyqtSignal(str, str)  # URL, message
    new_tab_detected = pyqtSignal(str)    # URL
    browser_state_changed = pyqtSignal(bool)  # isAlive

# Global signals instance
signals = WorkerSignals()