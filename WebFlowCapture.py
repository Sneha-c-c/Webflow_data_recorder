import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from neo4j import GraphDatabase
import psycopg2
import numpy as np
from sentence_transformers import SentenceTransformer
import subprocess
import os
import threading
import time
import networkx as nx
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QCheckBox
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
import warnings
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Disable SSL warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# Initialize embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Graph Database (Neo4j) Connection
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Welcome123$"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Vector Database (PostgreSQL with pgvector)
PG_CONN = psycopg2.connect(dbname="vector_db", user="harid", password="", host="localhost")
PG_CURSOR = PG_CONN.cursor()
PG_CURSOR.execute("""CREATE TABLE IF NOT EXISTS page_embeddings (url TEXT PRIMARY KEY, embedding vector(384));""")
PG_CONN.commit()

flows = {}
TARGET_WEBSITE = ""
G = nx.DiGraph()
browser = None
capture_thread = None
stop_capturing = False

# Create a signal class for thread communication
class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str, str)
    success = pyqtSignal(str)
    warning = pyqtSignal(str, str)
    update_status = pyqtSignal(str)

# Global signals instance
signals = WorkerSignals()

# Record user action
def record_action(url, metadata, content, referrer=None):
    if url not in flows:
        flows[url] = {"metadata": metadata, "content": content}
    G.add_node(url, metadata=metadata)
    
    # Add edge from referrer if available
    if referrer and referrer in flows:
        G.add_edge(referrer, url)
    
    # Store in databases
    store_in_neo4j(url, metadata, referrer)
    store_in_pgvector(url, content)

# Scrape Metadata
def extract_metadata(html):
    soup = BeautifulSoup(html, "html.parser")
    fields = [input_tag.get("name") for input_tag in soup.find_all("input")]
    actions = [btn.text.strip() for btn in soup.find_all("button")]
    forms = []
    for form in soup.find_all("form"):
        form_data = {
            "action": form.get("action", ""),
            "method": form.get("method", ""),
            "fields": [{"name": inp.get("name", ""), "type": inp.get("type", "")} for inp in form.find_all("input")]
        }
        forms.append(form_data)
    return {"fields": fields, "actions": actions, "forms": forms}

# Store in Neo4j
def store_in_neo4j(url, metadata, referrer=None):
    with driver.session() as session:
        # Create page node
        session.run("""
        MERGE (p:Page {url: $url})
        SET p.metadata = $metadata
        """, url=url, metadata=str(metadata))
        
        # Create relationship from referrer if available
        if referrer:
            session.run("""
            MATCH (r:Page {url: $referrer})
            MATCH (p:Page {url: $url})
            MERGE (r)-[:LEADS_TO]->(p)
            """, referrer=referrer, url=url)

# Store in Vector DB
def store_in_pgvector(url, content):
    embedding = model.encode(content).astype('float32')
    PG_CURSOR.execute("INSERT INTO page_embeddings (url, embedding) VALUES (%s, %s) ON CONFLICT (url) DO UPDATE SET embedding = %s;", 
                      (url, embedding.tolist(), embedding.tolist()))
    PG_CONN.commit()

# Check if browser is still alive
def is_browser_alive():
    global browser
    try:
        if browser is None:
            return False
        # A simple operation to check if browser is responsive
        browser.current_window_handle
        return True
    except:
        return False

# Initialize and start browser with Chrome DevTools Protocol enabled
def start_browser():
    global browser
    
    if is_browser_alive():
        # Browser already running
        return True
    
    try:
        # Configure Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--remote-debugging-port=9222")  # Enable DevTools Protocol
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option("detach", True)  # Keep browser open
        
        # Initialize browser - use default ChromeDriver location
        browser = webdriver.Chrome(options=chrome_options)
        
        # Test that browser is working
        browser.get("about:blank")
        
        return True
    except Exception as e:
        print(f"Error starting browser: {e}")
        signals.error.emit("Browser Error", f"Failed to start browser: {e}")
        return False

# Stop browser
def stop_browser():
    global browser, stop_capturing
    
    # First ensure capturing is stopped
    stop_capturing = True
    
    # Allow capture thread to finish
    time.sleep(1)
    
    # Now close the browser
    if browser:
        try:
            browser.quit()
        except Exception as e:
            print(f"Error closing browser: {e}")
        browser = None

# Continuously capture web actions
def capture_web_actions():
    global browser, stop_capturing, TARGET_WEBSITE
    
    if not TARGET_WEBSITE.startswith(('http://', 'https://')):
        TARGET_WEBSITE = 'https://' + TARGET_WEBSITE
    
    # Start by visiting the target website
    try:
        if browser is None or not is_browser_alive():
            signals.error.emit("Browser Error", "Browser is not running. Please start the browser first.")
            return
            
        browser.get(TARGET_WEBSITE)
        signals.update_status.emit(f"Opened target website: {TARGET_WEBSITE}")
        
        # Store initial page
        url = browser.current_url
        html_content = browser.page_source
        metadata = extract_metadata(html_content)
        record_action(url, metadata, html_content)
        
        last_url = url
        
        # Continuously monitor for page changes
        while not stop_capturing:
            # Check if browser is still active
            if not is_browser_alive():
                signals.error.emit("Browser Error", "Browser window was closed")
                break
                
            try:
                current_url = browser.current_url
                
                # If URL has changed, record the new page
                if current_url != last_url:
                    html_content = browser.page_source
                    metadata = extract_metadata(html_content)
                    record_action(current_url, metadata, html_content, last_url)
                    
                    signals.update_status.emit(f"Captured: {current_url}")
                    print(f"✓ Captured page: {current_url}")
                    
                    last_url = current_url
                
                # Check for AJAX updates on the same page
                if current_url == last_url:
                    html_content = browser.page_source
                    if html_content != flows.get(current_url, {}).get('content', ''):
                        metadata = extract_metadata(html_content)
                        record_action(current_url, metadata, html_content)
                        signals.update_status.emit(f"Updated: {current_url}")
                        print(f"✓ Updated page content: {current_url}")
                
                # Brief pause to avoid high CPU usage
                time.sleep(0.5)
                
            except Exception as e:
                # Handle WebDriver exceptions that can occur if the page is navigating
                print(f"Temporary error in capture loop: {e}")
                time.sleep(1)  # Give browser time to settle
                if not is_browser_alive():
                    break
            
    except Exception as e:
        print(f"Error in capture thread: {e}")
        signals.error.emit("Capture Error", f"Error capturing web actions: {e}")
    
    signals.update_status.emit("Capture thread stopped")

# Export captured data to visualization
def export_visualization():
    try:
        # Create a NetworkX graph visualization
        plt.figure(figsize=(12, 10))
        pos = nx.spring_layout(G)
        nx.draw(G, pos, with_labels=True, node_color='skyblue', node_size=1500, edge_color='gray', arrows=True)
        plt.title("Web Flow Capture")
        plt.savefig("web_flow_capture.png")
        plt.close()
        
        # Create a report
        report = "Web Flow Capture Report\n"
        report += "=" * 80 + "\n\n"
        report += f"Target Website: {TARGET_WEBSITE}\n"
        report += f"Total Pages Captured: {len(flows)}\n\n"
        
        for url, data in flows.items():
            report += f"URL: {url}\n"
            report += f"Fields: {data['metadata'].get('fields', [])}\n"
            report += f"Actions: {data['metadata'].get('actions', [])}\n"
            report += "-" * 80 + "\n"
        
        # Write report to file
        with open("web_flow_report.txt", "w") as f:
            f.write(report)
        
        return True
    except Exception as e:
        print(f"Error exporting visualization: {e}")
        return False

# PyQt5 UI Class
class WebFlowCaptureApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.connectSignals()
        self.is_capturing = False
    
    def initUI(self):
        self.setWindowTitle("Web Flow Capture")
        self.setGeometry(100, 100, 600, 400)
        
        layout = QVBoxLayout()
        
        # Target Website Input
        website_layout = QHBoxLayout()
        self.website_label = QLabel("Target Website:")
        self.website_entry = QLineEdit()
        self.website_entry.setPlaceholderText("example.com")
        self.website_entry.textChanged.connect(self.validate_inputs)
        website_layout.addWidget(self.website_label)
        website_layout.addWidget(self.website_entry)
        layout.addLayout(website_layout)
        
        # Browser Control Buttons
        browser_buttons_layout = QHBoxLayout()
        
        # Start Browser Button
        self.start_browser_button = QPushButton("Start Browser")
        self.start_browser_button.clicked.connect(self.start_browser_clicked)
        browser_buttons_layout.addWidget(self.start_browser_button)
        
        # Stop Browser Button
        self.stop_browser_button = QPushButton("Stop Browser")
        self.stop_browser_button.clicked.connect(self.stop_browser_clicked)
        self.stop_browser_button.setEnabled(False)
        browser_buttons_layout.addWidget(self.stop_browser_button)
        
        layout.addLayout(browser_buttons_layout)
        
        # Start/Stop Capturing Buttons
        capture_buttons_layout = QHBoxLayout()
        
        # Start Capturing Button
        self.start_capture_button = QPushButton("Start Capturing")
        self.start_capture_button.setEnabled(False)
        self.start_capture_button.clicked.connect(self.start_capturing)
        capture_buttons_layout.addWidget(self.start_capture_button)
        
        # Stop Capturing Button
        self.stop_capture_button = QPushButton("Stop Capturing")
        self.stop_capture_button.setEnabled(False)
        self.stop_capture_button.clicked.connect(self.stop_capturing)
        capture_buttons_layout.addWidget(self.stop_capture_button)
        
        # Export Data Button
        self.export_button = QPushButton("Export Data")
        self.export_button.clicked.connect(self.export_data)
        capture_buttons_layout.addWidget(self.export_button)
        
        layout.addLayout(capture_buttons_layout)
        
        # Instructions
        self.instructions_label = QLabel(
            "Instructions:\n"
            "1. Enter target website URL\n"
            "2. Click 'Start Browser' to launch a controlled Chrome browser\n"
            "3. Click 'Start Capturing' to begin recording web actions\n"
            "4. Browse normally in the opened browser window\n"
            "5. Click 'Stop Capturing' when finished\n"
            "6. Click 'Export Data' to generate reports"
        )
        self.instructions_label.setStyleSheet("background-color: #f0f0f0; padding: 10px;")
        layout.addWidget(self.instructions_label)
        
        # Status Label
        self.status_label = QLabel("Status: Not Started")
        layout.addWidget(self.status_label)
        
        # Capture Log
        self.log_label = QLabel("Capture Log:")
        layout.addWidget(self.log_label)
        
        self.log_area = QLabel("")
        self.log_area.setStyleSheet("background-color: #f0f0f0; padding: 10px; min-height: 100px;")
        self.log_area.setWordWrap(True)
        layout.addWidget(self.log_area)
        
        self.setLayout(layout)
    
    def connectSignals(self):
        # Connect worker signals to UI methods
        signals.success.connect(self.show_success)
        signals.error.connect(self.show_error)
        signals.warning.connect(self.show_warning)
        signals.update_status.connect(self.update_status)
    
    @pyqtSlot(str)
    def show_success(self, message):
        QMessageBox.information(self, "Success", message)
    
    @pyqtSlot(str, str)
    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)
    
    @pyqtSlot(str, str)
    def show_warning(self, title, message):
        QMessageBox.warning(self, title, message)
    
    @pyqtSlot(str)
    def update_status(self, message):
        current_log = self.log_area.text()
        if current_log:
            current_log += "\n"
        self.log_area.setText(current_log + message)
    
    def validate_inputs(self):
        website = self.website_entry.text().strip()
        if website and browser is not None:
            self.start_capture_button.setEnabled(True)
        else:
            self.start_capture_button.setEnabled(False)
    
    def start_browser_clicked(self):
        if start_browser():
            self.status_label.setText("Status: Browser Running")
            self.start_browser_button.setEnabled(False)
            self.stop_browser_button.setEnabled(True)
            self.validate_inputs()
            self.update_status("Browser started successfully")
        else:
            self.status_label.setText("Status: Browser Failed to Start")
    
    def stop_browser_clicked(self):
        # Ensure capturing is stopped first
        if self.is_capturing:
            self.stop_capturing()
        
        stop_browser()
        self.status_label.setText("Status: Browser Stopped")
        self.start_browser_button.setEnabled(True)
        self.stop_browser_button.setEnabled(False)
        self.start_capture_button.setEnabled(False)
        self.update_status("Browser stopped")
    
    def start_capturing(self):
        global TARGET_WEBSITE, stop_capturing, capture_thread
        
        # Check if browser is running first
        if not is_browser_alive():
            self.show_error("Browser Error", "Browser is not running. Please start the browser first.")
            return
            
        TARGET_WEBSITE = self.website_entry.text()
        stop_capturing = False
        
        self.is_capturing = True
        self.stop_capture_button.setEnabled(True)
        self.start_capture_button.setEnabled(False)
        
        # Start capturing thread
        capture_thread = threading.Thread(target=capture_web_actions, daemon=True)
        capture_thread.start()
        
        # Update UI
        self.update_status(f"Started capturing for {TARGET_WEBSITE}")
        self.status_label.setText("Status: Capturing web flows")
    
    def stop_capturing(self):
        global stop_capturing
        
        stop_capturing = True
        self.is_capturing = False
        self.stop_capture_button.setEnabled(False)
        
        if browser is not None:
            self.start_capture_button.setEnabled(True)
        
        # Update UI
        self.update_status("Stopping capture...")
        self.status_label.setText("Status: Capture stopped")
        
        # Wait for thread to end
        if capture_thread and capture_thread.is_alive():
            capture_thread.join(timeout=2)
    
    def export_data(self):
        if export_visualization():
            self.show_success("Data exported successfully. Check web_flow_capture.png and web_flow_report.txt")
        else:
            self.show_error("Export Error", "Failed to export data")
    
    def closeEvent(self, event):
        global stop_capturing
        
        stop_capturing = True
        stop_browser()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = WebFlowCaptureApp()
    window.show()
    
    sys.exit(app.exec_())