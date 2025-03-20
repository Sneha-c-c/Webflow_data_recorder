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
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox
import warnings

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
PROXY_PORT = "9080"
G = nx.DiGraph()
proxy_process = None

# Proxy Server for Recording Actions
def record_action(url, metadata, content):
    if url not in flows:
        flows[url] = {"metadata": metadata, "content": content}
    G.add_node(url, metadata=metadata)
    
    # Store in databases
    store_in_neo4j(url, metadata)
    store_in_pgvector(url, content)

# Scrape Metadata
def extract_metadata(html):
    soup = BeautifulSoup(html, "html.parser")
    fields = [input_tag.get("name") for input_tag in soup.find_all("input")]
    actions = [btn.text.strip() for btn in soup.find_all("button")]
    return {"fields": fields, "actions": actions}

# Store in Neo4j
def store_in_neo4j(url, metadata):
    with driver.session() as session:
        session.run("""
        MERGE (p:Page {url: $url})
        SET p.metadata = $metadata
        """, url=url, metadata=str(metadata))

# Store in Vector DB
def store_in_pgvector(url, content):
    embedding = model.encode(content).astype('float32')
    PG_CURSOR.execute("INSERT INTO page_embeddings (url, embedding) VALUES (%s, %s) ON CONFLICT (url) DO NOTHING;", (url, embedding.tolist()))
    PG_CONN.commit()

# Start proxy server using command line
def start_proxy():
    global proxy_process
    print("Starting Proxy Server...")
    try:
        # Use mitmdump instead of mitmweb for better headless operation
        proxy_process = subprocess.Popen(
            ["mitmdump", "-p", PROXY_PORT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"Proxy process started with PID: {proxy_process.pid}")
        
        # Wait for proxy to start
        time.sleep(5)
        
        # Check if process is running
        if proxy_process.poll() is None:
            print("✓ Proxy server started successfully")
            return True
        else:
            print(f"❌ Proxy failed to start. Return code: {proxy_process.poll()}")
            stdout, stderr = proxy_process.communicate(timeout=1)
            print(f"STDOUT: {stdout[:200]}...")
            print(f"STDERR: {stderr[:200]}...")
            return False
    except Exception as e:
        print(f"❌ Error starting proxy: {e}")
        return False

# Check if proxy is running
def is_proxy_running():
    global proxy_process
    
    # First check if the process is still running
    if proxy_process and proxy_process.poll() is None:
        # Try to connect to the proxy
        try:
            # Test connection to proxy by making a simple request
            proxies = {
                "http": f"http://127.0.0.1:{PROXY_PORT}",
                "https": f"http://127.0.0.1:{PROXY_PORT}"
            }
            response = requests.get("http://example.com", proxies=proxies, timeout=5, verify=False)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    return False

# Kill proxy process when program exits
def stop_proxy():
    global proxy_process
    if proxy_process:
        print("Stopping Proxy Server...")
        proxy_process.terminate()
        try:
            proxy_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proxy_process.kill()
            proxy_process.wait()

# Manually send target website requests via proxy
def fetch_target_page():
    global TARGET_WEBSITE
    
    if not TARGET_WEBSITE.startswith(('http://', 'https://')):
        TARGET_WEBSITE = 'https://' + TARGET_WEBSITE
    
    proxies = {
        "http": f"http://127.0.0.1:{PROXY_PORT}",
        "https": f"http://127.0.0.1:{PROXY_PORT}"
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    # Start proxy if not already started
    if not is_proxy_running():
        if not start_proxy():
            QMessageBox.critical(None, "Proxy Error", "Failed to start proxy server")
            return
    
    try:
        print(f"Sending request to {TARGET_WEBSITE} via proxy...")
        response = requests.get(TARGET_WEBSITE, proxies=proxies, headers=headers, verify=False, timeout=30)
        
        if response.status_code == 200:
            html_content = response.text
            metadata = extract_metadata(html_content)
            record_action(TARGET_WEBSITE, metadata, html_content)
            print(f"✓ Successfully captured: {TARGET_WEBSITE}")
            QMessageBox.information(None, "Success", f"Successfully captured data from {TARGET_WEBSITE}")
        else:
            error_msg = f"Failed to fetch {TARGET_WEBSITE}: Status code {response.status_code}"
            print(error_msg)
            QMessageBox.warning(None, "Request Failed", error_msg)
    except requests.exceptions.ProxyError as e:
        error_msg = f"❌ Proxy Connection Failed: {e}"
        print(error_msg)
        QMessageBox.critical(None, "Proxy Error", error_msg)
    except requests.exceptions.Timeout:
        error_msg = f"❌ Request timed out while fetching {TARGET_WEBSITE}"
        print(error_msg)
        QMessageBox.warning(None, "Timeout", error_msg)
    except Exception as e:
        error_msg = f"⚠️ Error fetching {TARGET_WEBSITE}: {e}"
        print(error_msg)
        QMessageBox.critical(None, "Error", error_msg)

# PyQt5 UI Class
class ProxyConfigApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("Web Flow Capture")
        self.setGeometry(100, 100, 500, 300)
        
        layout = QVBoxLayout()
        
        # Proxy Port Input
        port_layout = QHBoxLayout()
        self.port_label = QLabel("Proxy Port:")
        self.port_entry = QLineEdit()
        self.port_entry.setText(PROXY_PORT)
        self.port_entry.textChanged.connect(self.update_port)
        port_layout.addWidget(self.port_label)
        port_layout.addWidget(self.port_entry)
        layout.addLayout(port_layout)
        
        # Target Website Input
        website_layout = QHBoxLayout()
        self.website_label = QLabel("Target Website:")
        self.website_entry = QLineEdit()
        self.website_entry.setPlaceholderText("example.com")
        self.website_entry.textChanged.connect(self.validate_inputs)
        website_layout.addWidget(self.website_label)
        website_layout.addWidget(self.website_entry)
        layout.addLayout(website_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        # Start Proxy Button
        self.start_proxy_button = QPushButton("Start Proxy")
        self.start_proxy_button.clicked.connect(self.start_proxy_clicked)
        buttons_layout.addWidget(self.start_proxy_button)
        
        # Check Proxy Status Button
        self.check_proxy_button = QPushButton("Check Proxy Status")
        self.check_proxy_button.clicked.connect(self.check_proxy_status)
        buttons_layout.addWidget(self.check_proxy_button)
        
        # Stop Proxy Button
        self.stop_proxy_button = QPushButton("Stop Proxy")
        self.stop_proxy_button.clicked.connect(self.stop_proxy_clicked)
        buttons_layout.addWidget(self.stop_proxy_button)
        
        layout.addLayout(buttons_layout)
        
        # Start Scraping Button
        self.start_scraping_button = QPushButton("Fetch Target Website")
        self.start_scraping_button.setEnabled(False)
        self.start_scraping_button.clicked.connect(self.start_scraping)
        layout.addWidget(self.start_scraping_button)
        
        # Status Label
        self.status_label = QLabel("Proxy Status: Not Started")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
    
    def update_port(self):
        global PROXY_PORT
        PROXY_PORT = self.port_entry.text()
        self.validate_inputs()
    
    def validate_inputs(self):
        if self.website_entry.text().strip():
            self.start_scraping_button.setEnabled(True)
        else:
            self.start_scraping_button.setEnabled(False)
    
    def start_proxy_clicked(self):
        if start_proxy():
            self.status_label.setText("Proxy Status: Running")
        else:
            self.status_label.setText("Proxy Status: Failed to Start")
    
    def check_proxy_status(self):
        if is_proxy_running():
            self.status_label.setText("Proxy Status: Running")
            QMessageBox.information(self, "Proxy Status", "Proxy is running")
        else:
            self.status_label.setText("Proxy Status: Not Running")
            QMessageBox.warning(self, "Proxy Status", "Proxy is not running")
    
    def stop_proxy_clicked(self):
        stop_proxy()
        self.status_label.setText("Proxy Status: Stopped")
    
    def start_scraping(self):
        global TARGET_WEBSITE
        TARGET_WEBSITE = self.website_entry.text()
        threading.Thread(target=fetch_target_page, daemon=True).start()
    
    def closeEvent(self, event):
        stop_proxy()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ProxyConfigApp()
    window.show()
    
    # Clean up resources on exit
    atexit_app = lambda: stop_proxy()
    app.aboutToQuit.connect(atexit_app)
    
    sys.exit(app.exec_())