from PyQt5.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
                           QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
                           QLineEdit, QMessageBox, QMenu, QAction, QInputDialog,
                           QDateEdit, QGroupBox, QGridLayout, QCheckBox, QScrollArea,
                           QWidget, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QDate
from PyQt5.QtGui import QFont, QIcon, QCursor
import csv
from datetime import datetime, timedelta

from database.history_manager import history_manager
from ui.flow_dialog import FlowVisualizationDialog

class SessionHistoryDialog(QDialog):
    sessionSelected = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.filtered_sessions = []
        self.initUI()
        self.loadSessions()
    
    def initUI(self):
        self.setWindowTitle("Capture Session History")
        
        # If parent exists, set size relative to parent
        if self.parent:
            parent_width = self.parent.width()
            parent_height = self.parent.height()
            self.setGeometry(0, 0, int(parent_width * 0.9), int(parent_height * 0.9))
            # Center the dialog on the parent
            self.move(
                self.parent.x() + int((parent_width - self.width()) / 2),
                self.parent.y() + int((parent_height - self.height()) / 2)
            )
        else:
            self.setGeometry(100, 100, 900, 650)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header = QLabel("Web Flow Capture History")
        header.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(header)
        
        # Create a scroll area for the entire content
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_container = QWidget()
        main_scroll_layout = QVBoxLayout(main_container)
        main_scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        # Filter and search controls in a group box
        filter_group = QGroupBox("Search & Filter")
        filter_layout = QGridLayout()
        
        # Website search
        search_label = QLabel("Search by website:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter website name...")
        self.search_input.textChanged.connect(self.applyFilters)
        filter_layout.addWidget(search_label, 0, 0)
        filter_layout.addWidget(self.search_input, 0, 1)
        
        # Date filters
        date_from_label = QLabel("From date:")
        self.date_from = QDateEdit(calendarPopup=True)
        # Set default to 30 days ago
        default_from = QDate.currentDate().addDays(-30)
        self.date_from.setDate(default_from)
        self.date_from.dateChanged.connect(self.applyFilters)
        filter_layout.addWidget(date_from_label, 0, 2)
        filter_layout.addWidget(self.date_from, 0, 3)
        
        date_to_label = QLabel("To date:")
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDate(QDate.currentDate())  # Today's date
        self.date_to.dateChanged.connect(self.applyFilters)
        filter_layout.addWidget(date_to_label, 0, 4)
        filter_layout.addWidget(self.date_to, 0, 5)
        
        # Use date filter checkbox
        self.use_date_filter = QCheckBox("Use date filter")
        self.use_date_filter.setChecked(False)
        self.use_date_filter.stateChanged.connect(self.applyFilters)
        filter_layout.addWidget(self.use_date_filter, 0, 6)
        
        # Sort options
        sort_label = QLabel("Sort by:")
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Date (newest first)", "Date (oldest first)", 
                                  "Website (A-Z)", "Website (Z-A)",
                                  "Pages (most first)", "Pages (least first)"])
        self.sort_combo.currentIndexChanged.connect(self.applyFilters)
        filter_layout.addWidget(sort_label, 1, 0)
        filter_layout.addWidget(self.sort_combo, 1, 1)
        
        # Reset filters button
        self.reset_button = QPushButton("Reset Filters")
        self.reset_button.clicked.connect(self.resetFilters)
        filter_layout.addWidget(self.reset_button, 1, 2, 1, 2)
        
        # Export button
        self.export_button = QPushButton("Export Sessions")
        self.export_button.clicked.connect(self.exportSessions)
        filter_layout.addWidget(self.export_button, 1, 4, 1, 2)
        
        filter_group.setLayout(filter_layout)
        main_scroll_layout.addWidget(filter_group)
        
        # Sessions table
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(6)
        self.sessions_table.setHorizontalHeaderLabels(["Website", "Start Time", "End Time", "Duration", "Pages", "Description"])
        self.sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.sessions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)  # Website column stretches
        self.sessions_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)  # Description column stretches
        self.sessions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sessions_table.setSelectionMode(QTableWidget.SingleSelection)
        self.sessions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sessions_table.setAlternatingRowColors(True)
        self.sessions_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sessions_table.customContextMenuRequested.connect(self.showContextMenu)
        self.sessions_table.cellDoubleClicked.connect(self.onSessionDoubleClicked)
        self.sessions_table.setMinimumHeight(300)  # Set minimum height
        main_scroll_layout.addWidget(self.sessions_table)
        
        # Status label
        self.status_label = QLabel("Showing all sessions")
        self.status_label.setAlignment(Qt.AlignLeft)
        main_scroll_layout.addWidget(self.status_label)
        
        # Set the main container as the widget for the scroll area
        main_scroll.setWidget(main_container)
        
        # Add the scroll area to the main layout
        layout.addWidget(main_scroll)
        
        # Buttons at the bottom (outside the scroll area)
        buttons_layout = QHBoxLayout()
        
        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.loadSessions)
        buttons_layout.addWidget(self.refresh_button)
        
        # Delete selected button
        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.clicked.connect(self.deleteSelectedSession)
        buttons_layout.addWidget(self.delete_button)
        
        # View selected button
        self.view_button = QPushButton("View Selected")
        self.view_button.clicked.connect(self.viewSelectedSession)
        buttons_layout.addWidget(self.view_button)
        
        # Add description button
        self.add_desc_button = QPushButton("Add Description")
        self.add_desc_button.clicked.connect(self.addDescriptionToSession)
        buttons_layout.addWidget(self.add_desc_button)
        
        # Close button
        buttons_layout.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.close_button)
        
        layout.addLayout(buttons_layout)
    
    def resetFilters(self):
        """Reset all filters to default values"""
        self.search_input.clear()
        default_from = QDate.currentDate().addDays(-30)
        self.date_from.setDate(default_from)
        self.date_to.setDate(QDate.currentDate())
        self.use_date_filter.setChecked(False)
        self.sort_combo.setCurrentIndex(0)  # Date newest first
        self.loadSessions()
    
    def loadSessions(self):
        """Load all sessions into the table"""
        # Get all sessions from the history manager
        all_sessions = history_manager.get_all_sessions()
        
        # Apply filters to get filtered sessions
        self.applyFilters()
    
    def applyFilters(self):
        """Apply all filters to sessions"""
        # Get all sessions
        all_sessions = history_manager.get_all_sessions()
        
        # Apply website search filter
        search_text = self.search_input.text().strip().lower()
        if search_text:
            all_sessions = [s for s in all_sessions if s.website and search_text in s.website.lower()]
        
        # Apply date filter if enabled
        if self.use_date_filter.isChecked():
            from_date = self.date_from.date().toPyDate()
            to_date = self.date_to.date().toPyDate()
            
            # Convert to timestamp (with time component)
            from_timestamp = datetime.combine(from_date, datetime.min.time()).timestamp()
            to_timestamp = datetime.combine(to_date, datetime.max.time()).timestamp()
            
            all_sessions = [s for s in all_sessions if from_timestamp <= s.start_time <= to_timestamp]
        
        # Apply current sorting
        sort_index = self.sort_combo.currentIndex()
        if sort_index == 0:  # Date (newest first)
            all_sessions = sorted(all_sessions, key=lambda s: s.start_time, reverse=True)
        elif sort_index == 1:  # Date (oldest first)
            all_sessions = sorted(all_sessions, key=lambda s: s.start_time, reverse=False)
        elif sort_index == 2:  # Website (A-Z)
            all_sessions = sorted(all_sessions, key=lambda s: s.website.lower() if s.website else "")
        elif sort_index == 3:  # Website (Z-A)
            all_sessions = sorted(all_sessions, key=lambda s: s.website.lower() if s.website else "", reverse=True)
        elif sort_index == 4:  # Pages (most first)
            all_sessions = sorted(all_sessions, key=lambda s: s.page_count, reverse=True)
        elif sort_index == 5:  # Pages (least first)
            all_sessions = sorted(all_sessions, key=lambda s: s.page_count, reverse=False)
        
        # Save the filtered sessions
        self.filtered_sessions = all_sessions
        
        # Update the UI
        self.updateSessionsTable()
    
    def updateSessionsTable(self):
        """Update the sessions table with filtered sessions"""
        # Set up table
        self.sessions_table.setRowCount(len(self.filtered_sessions))
        
        # Populate table
        for row, session in enumerate(self.filtered_sessions):
            # Add the session ID as hidden data
            website_item = QTableWidgetItem(session.website or "Unknown")
            website_item.setData(Qt.UserRole, session.id)
            self.sessions_table.setItem(row, 0, website_item)
            
            # Add other session data
            self.sessions_table.setItem(row, 1, QTableWidgetItem(session.formatted_start_time))
            self.sessions_table.setItem(row, 2, QTableWidgetItem(session.formatted_end_time))
            self.sessions_table.setItem(row, 3, QTableWidgetItem(session.duration))
            
            page_count_item = QTableWidgetItem(str(session.page_count))
            page_count_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 4, page_count_item)
            
            self.sessions_table.setItem(row, 5, QTableWidgetItem(session.description))
        
        # Update status label
        if not self.filtered_sessions:
            self.status_label.setText("No sessions found")
        else:
            filter_text = ""
            if self.search_input.text().strip():
                filter_text += f" | Search: '{self.search_input.text().strip()}'"
            
            if self.use_date_filter.isChecked():
                from_date = self.date_from.date().toString("yyyy-MM-dd")
                to_date = self.date_to.date().toString("yyyy-MM-dd")
                filter_text += f" | Date range: {from_date} to {to_date}"
                
            if filter_text:
                self.status_label.setText(f"Showing {len(self.filtered_sessions)} sessions{filter_text}")
            else:
                self.status_label.setText(f"Showing all {len(self.filtered_sessions)} sessions")
        
        # Enable/disable buttons based on selection
        has_selection = len(self.filtered_sessions) > 0
        self.view_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.add_desc_button.setEnabled(has_selection)
        self.export_button.setEnabled(len(self.filtered_sessions) > 0)
    
    def showContextMenu(self, position):
        """Show context menu for session row"""
        # Check if a row is selected
        if not self.sessions_table.selectedItems():
            return
        
        # Create context menu
        context_menu = QMenu(self)
        
        # Add actions
        view_action = QAction("View Session", self)
        view_action.triggered.connect(self.viewSelectedSession)
        context_menu.addAction(view_action)
        
        add_desc_action = QAction("Add Description", self)
        add_desc_action.triggered.connect(self.addDescriptionToSession)
        context_menu.addAction(add_desc_action)
        
        delete_action = QAction("Delete Session", self)
        delete_action.triggered.connect(self.deleteSelectedSession)
        context_menu.addAction(delete_action)
        
        # Show context menu
        context_menu.exec_(QCursor.pos())
    
    def getSelectedSessionId(self):
        """Get ID of the selected session"""
        selected_items = self.sessions_table.selectedItems()
        if not selected_items:
            return None
        
        # Get the selected row
        row = selected_items[0].row()
        
        # Get the session ID from the hidden data
        session_id = self.sessions_table.item(row, 0).data(Qt.UserRole)
        return session_id
    
    def viewSelectedSession(self):
        """View the selected session"""
        session_id = self.getSelectedSessionId()
        if not session_id:
            QMessageBox.warning(self, "No Selection", "Please select a session first")
            return
        
        # Emit signal with session ID
        self.sessionSelected.emit(session_id)
        
        # Open flow visualization dialog
        flow_dialog = FlowVisualizationDialog(self.parent, session_id)
        flow_dialog.exec_()
    
    def onSessionDoubleClicked(self, row, column):
        """Handle double-click on session row"""
        # Get session ID from the row
        session_id = self.sessions_table.item(row, 0).data(Qt.UserRole)
        
        # Emit signal with session ID
        self.sessionSelected.emit(session_id)
        
        # Open flow visualization dialog
        flow_dialog = FlowVisualizationDialog(self.parent, session_id)
        flow_dialog.exec_()
    
    def deleteSelectedSession(self):
        """Delete the selected session"""
        session_id = self.getSelectedSessionId()
        if not session_id:
            QMessageBox.warning(self, "No Selection", "Please select a session first")
            return
        
        # Confirm deletion
        reply = QMessageBox.question(self, "Confirm Deletion", 
                                     "Are you sure you want to delete this session?\nThis will remove all captured data.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Delete session
            success = history_manager.delete_session(session_id)
            
            if success:
                QMessageBox.information(self, "Success", "Session deleted successfully")
                self.loadSessions()
            else:
                QMessageBox.warning(self, "Error", "Failed to delete session")
    
    def addDescriptionToSession(self):
        """Add or update description for the selected session"""
        session_id = self.getSelectedSessionId()
        if not session_id:
            QMessageBox.warning(self, "No Selection", "Please select a session first")
            return
        
        # Get the current description
        session = history_manager.get_session_by_id(session_id)
        if not session:
            QMessageBox.warning(self, "Error", "Session not found")
            return
        
        # Get new description from user
        current_desc = session.description
        new_desc, ok = QInputDialog.getText(self, "Add Description", 
                                          "Enter session description:", 
                                          QLineEdit.Normal, 
                                          current_desc)
        
        if ok:
            # Update session
            success = history_manager.update_session(session_id, description=new_desc)
            
            if success:
                self.loadSessions()
            else:
                QMessageBox.warning(self, "Error", "Failed to update session")
    
    def exportSessions(self):
        """Export sessions to CSV"""
        if not self.filtered_sessions:
            QMessageBox.information(self, "No Data", "There are no sessions to export.")
            return
        
        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"sessions_{timestamp}.csv"
        
        # Ask user for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Sessions CSV", default_filename, "CSV Files (*.csv)"
        )
        
        if not file_path:
            return  # User canceled
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                # Create CSV writer
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow([
                    "Session ID", "Website", "Start Time", "End Time", 
                    "Duration", "Page Count", "Description"
                ])
                
                # Write data for each session
                for session in self.filtered_sessions:
                    writer.writerow([
                        session.id,
                        session.website or "Unknown",
                        session.formatted_start_time,
                        session.formatted_end_time,
                        session.duration,
                        session.page_count,
                        session.description
                    ])
            
            QMessageBox.information(self, "Export Successful", f"Sessions exported to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error exporting sessions: {str(e)}")