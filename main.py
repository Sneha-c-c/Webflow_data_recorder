#!/usr/bin/env python3
import sys
import warnings
import os
from PyQt5.QtWidgets import QApplication
import atexit

from ui.app_window import WebFlowCaptureApp
from browser.controller import stop_browser
from database.graph_db import close_neo4j_connection
from database.vector_db import close_pg_connection

# Disable SSL warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

def setup_directories():
    """Create necessary directories if they don't exist"""
    os.makedirs("captured_data", exist_ok=True)
    
def cleanup():
    """Cleanup function to be called on exit"""
    print("Cleaning up resources...")
    stop_browser()
    close_neo4j_connection()
    close_pg_connection()

def main():
    # Setup directories
    setup_directories()
    
    # Start application
    app = QApplication(sys.argv)
    window = WebFlowCaptureApp()
    window.show()
    
    # Register cleanup function
    atexit.register(cleanup)
    
    # Start event loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()