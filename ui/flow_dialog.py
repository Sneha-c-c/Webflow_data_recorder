from PyQt5.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout, QTreeWidget, QTreeWidgetItem, QSplitter,
                             QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
                             QTextBrowser, QWidget, QFileDialog, QMessageBox)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont
import csv
import os
from datetime import datetime

from database.graph_db import get_flow_data, get_page_details


class FlowVisualizationDialog(QDialog):
    pageSelected = pyqtSignal(str)

    def __init__(self, parent=None, session_id=None):
        super().__init__(parent)
        self.parent = parent
        self.session_id = session_id
        self.flows = []
        self.initUI()
        self.loadData()

    def initUI(self):
        self.setWindowTitle("Web Flow Visualization")

        # If parent exists, set size relative to parent
        if self.parent:
            parent_width = self.parent.width()
            parent_height = self.parent.height()
            self.setGeometry(0, 0, int(parent_width * 0.9),
                             int(parent_height * 0.9))
            # Center the dialog on the parent
            self.move(
                self.parent.x() + int((parent_width - self.width()) / 2),
                self.parent.y() + int((parent_height - self.height()) / 2)
            )
        else:
            self.setGeometry(100, 100, 900, 650)

        # Main layout with proper spacing and margins
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        if self.session_id:
            header = QLabel(f"Captured Web Flows - Session {self.session_id}")
        else:
            header = QLabel("Captured Web Flows")

        header.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(header)

        # Create a scroll area for the entire content
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_container = QWidget()
        main_scroll_layout = QVBoxLayout(main_container)
        main_scroll_layout.setContentsMargins(0, 0, 0, 0)

        # Create a splitter for resizable sections
        splitter = QSplitter(Qt.Horizontal)
        # Prevent sections from being collapsed completely
        splitter.setChildrenCollapsible(False)

        # Flow list - left side
        self.flow_list = QTreeWidget()
        self.flow_list.setHeaderLabels(["Path", "Details"])
        self.flow_list.setColumnWidth(0, 450)  # Wider first column
        self.flow_list.itemClicked.connect(self.flowItemClicked)
        self.flow_list.setAlternatingRowColors(True)
        # Minimum width to ensure readability
        self.flow_list.setMinimumWidth(450)
        splitter.addWidget(self.flow_list)

        # Page preview section - right side
        preview_container = QScrollArea()
        preview_container.setWidgetResizable(True)
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)

        # Preview header
        preview_header = QLabel("Page Details")
        preview_header.setFont(QFont("Arial", 12, QFont.Bold))
        preview_layout.addWidget(preview_header)

        # URL display
        self.preview_url = QTextBrowser()
        self.preview_url.setMaximumHeight(60)
        self.preview_url.setPlaceholderText("URL will appear here")
        preview_layout.addWidget(self.preview_url)

        # Preview table
        self.page_preview = QTableWidget()
        self.page_preview.setColumnCount(2)
        self.page_preview.setHorizontalHeaderLabels(["Property", "Value"])
        self.page_preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.page_preview.setAlternatingRowColors(True)
        self.page_preview.verticalHeader().setVisible(False)
        self.page_preview.setMinimumWidth(300)  # Minimum width for the preview
        preview_layout.addWidget(self.page_preview)

        # View full details button
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        self.view_details_btn = QPushButton("View Full Details")
        self.view_details_btn.clicked.connect(self.viewFullDetails)
        self.view_details_btn.setEnabled(False)
        button_layout.addWidget(self.view_details_btn)

        preview_layout.addLayout(button_layout)

        preview_container.setWidget(preview_widget)
        splitter.addWidget(preview_container)

        # Set initial splitter sizes (60% left, 40% right)
        splitter.setSizes([600, 400])

        # Add splitter to main scroll layout
        main_scroll_layout.addWidget(splitter)

        # Export buttons
        export_layout = QHBoxLayout()
        export_layout.addStretch(1)

        self.export_flows_button = QPushButton("Export Flows to CSV")
        self.export_flows_button.clicked.connect(self.exportFlowsToCSV)
        self.export_flows_button.setEnabled(False)
        export_layout.addWidget(self.export_flows_button)

        main_scroll_layout.addLayout(export_layout)

        # Set the main container as the widget for the scroll area
        main_scroll.setWidget(main_container)

        # Add the scroll area to the main layout
        layout.addWidget(main_scroll)

        # Buttons at the bottom (outside the scroll area)
        buttons_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh Data")
        self.refresh_button.clicked.connect(self.loadData)
        buttons_layout.addWidget(self.refresh_button)

        # Add spacer
        buttons_layout.addStretch(1)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.close_button)

        layout.addLayout(buttons_layout)

    def loadData(self):
        # Clear existing items
        self.flow_list.clear()
        self.page_preview.setRowCount(0)
        self.preview_url.clear()
        self.view_details_btn.setEnabled(False)

        # Get flow data from Neo4j
        self.flows = get_flow_data(self.session_id)

        if not self.flows:
            # No flows found
            no_data_item = QTreeWidgetItem(self.flow_list)
            no_data_item.setText(0, "No flow data available")
            no_data_item.setText(1, "Capture some web flows first")
            self.addPreviewRow("Status", "No flow data available")
            self.addPreviewRow("Tip", "Start capturing to record web flows")
            self.export_flows_button.setEnabled(False)
            return

        # Enable export button if flows exist
        self.export_flows_button.setEnabled(True)

        # Add flows to tree widget
        for flow_index, flow_path in enumerate(self.flows):
            # Create flow item
            flow_item = QTreeWidgetItem(self.flow_list)
            flow_item.setText(0, f"Flow {flow_index + 1}")
            flow_item.setText(1, f"{len(flow_path)} steps")

            # Add each step in the flow
            for step_index, step in enumerate(flow_path):
                step_item = QTreeWidgetItem(flow_item)

                # Format the step text
                from_title = step.get('from_title', 'Unknown')
                to_title = step.get('to_title', 'Unknown')

                # Truncate long titles
                if len(from_title) > 30:
                    from_title = from_title[:27] + "..."
                if len(to_title) > 30:
                    to_title = to_title[:27] + "..."

                step_item.setText(0, f"{from_title} → {to_title}")
                step_item.setText(1, f"Step {step_index + 1}")

                # Store URL data for both from and to
                step_item.setData(0, Qt.UserRole, step.get(
                    'to_url', ''))  # Primary URL (to)
                step_item.setData(1, Qt.UserRole, step.get(
                    'from_url', ''))  # Secondary URL (from)

        self.flow_list.expandAll()

        # Add summary in preview
        self.addPreviewRow("Total Flows", str(len(self.flows)))
        self.addPreviewRow("Total Steps", str(sum(len(flow)
                           for flow in self.flows)))
        self.addPreviewRow("Instructions", "Click on any step to view details")

    def flowItemClicked(self, item, column):
        # Get URL from item data
        url = item.data(0, Qt.UserRole)
        if url:
            # Set the URL in the preview
            self.preview_url.setText(url)

            # Load preview data
            self.loadPagePreview(url)

            # Enable the view button
            self.view_details_btn.setEnabled(True)

    def loadPagePreview(self, url):
        """Load a preview of the page details in the right panel with enhanced field display"""
        # Clear current preview
        self.page_preview.setRowCount(0)

        # Get page details from Neo4j
        page_details = get_page_details(url)
        if not page_details:
            self.addPreviewRow("Error", "Page details not found")
            return

        # Add basic information
        self.addPreviewRow("Title", page_details.get("title", "Unknown"))
        self.addPreviewRow("Timestamp", str(page_details.get(
            "timestamp_readable", page_details.get("timestamp", ""))))

        # Add summary if available
        summary = page_details.get("summary", "")
        if summary:
            if len(summary) > 200:
                summary = summary[:200] + "..."
            self.addPreviewRow("Summary", summary)

        # Check if it's an alert
        if page_details.get("is_alert", False):
            self.addPreviewRow("Type", "JavaScript Alert")

        # Add enhanced field statistics with detailed breakdown
        self.addPreviewRow("═══ ENHANCED FIELD DETECTION ═══", "")
        self.addPreviewRow("🔢 Total Fields Found", str(
            page_details.get("total_fields", 0)))
        self.addPreviewRow("🏷️ Named Fields", str(
            page_details.get("named_fields", 0)))
        self.addPreviewRow("🆔 ID Fields", str(
            page_details.get("id_fields", 0)))
        self.addPreviewRow("💬 Placeholder Fields", str(
            page_details.get("placeholder_fields", 0)))
        self.addPreviewRow("⚠️ Required Fields", str(
            page_details.get("required_fields", 0)))
        self.addPreviewRow("♿ ARIA Labeled Fields", str(
            page_details.get("aria_labeled_fields", 0)))
        self.addPreviewRow("🎨 Class-based Fields",
                           str(page_details.get("class_fields", 0)))
        self.addPreviewRow("📊 Data Attribute Fields", str(
            page_details.get("data_attribute_fields", 0)))

        # Show detection method
        if page_details.get("enhanced_with_selenium", False):
            self.addPreviewRow("🔍 Detection Method",
                               "✅ Selenium + Shadow DOM + HTML")
            selenium_fields = page_details.get("selenium_fields", 0)
            shadow_fields = page_details.get("shadow_dom_fields", 0)
            if selenium_fields > 0:
                self.addPreviewRow("  └─ Selenium Detected",
                                   str(selenium_fields))
            if shadow_fields > 0:
                self.addPreviewRow(
                    "  └─ Shadow DOM Detected", str(shadow_fields))
        else:
            self.addPreviewRow("🔍 Detection Method", "HTML Parsing Only")

        # Add input type breakdown
        field_summary = page_details.get("field_summary", {})
        input_types = field_summary.get("input_types", {})
        if input_types:
            self.addPreviewRow("═══ FIELD TYPES BREAKDOWN ═══", "")
            for field_type, count in sorted(input_types.items()):
                icon = "🔤" if field_type in ["text", "email", "password"] else "☑️" if field_type in [
                    "checkbox", "radio"] else "🔢" if field_type == "number" else "📅" if field_type in ["date", "datetime"] else "🎯"
                self.addPreviewRow(
                    f"  {icon} {field_type.capitalize()}", str(count))

        # Add comprehensive form analysis
        forms = page_details.get("forms", [])
        self.addPreviewRow("═══ FORM ANALYSIS ═══", "")
        self.addPreviewRow("📝 Forms Detected", str(len(forms)))

        if forms:
            total_form_fields = 0
            forms_with_action = 0
            forms_with_names = 0

            for i, form in enumerate(forms[:5]):  # Show first 5 forms
                form_name = form.get("form_name", "") or form.get(
                    "form_id", "") or f"Form {i+1}"
                action = form.get("action", "No action")
                method = form.get("method", "GET").upper()
                field_count = form.get("field_count", 0)

                # Count statistics
                total_form_fields += field_count
                if action and action != "No action":
                    forms_with_action += 1
                if form.get("form_name", "") or form.get("form_id", ""):
                    forms_with_names += 1

                # Display form details with better formatting
                form_display = f"{method} → {action[:40]}{'...' if len(action) > 40 else ''} ({field_count} fields)"
                self.addPreviewRow(f"  📋 {form_name}", form_display)

                # Show field names if available
                if hasattr(form, 'field_details') or 'fields' in form:
                    field_names = []

                    # Try to get field names from different sources
                    if 'field_details' in form and form['field_details']:
                        field_names = [
                            f.get('name', '') for f in form['field_details'] if f.get('name')]
                    elif isinstance(form.get('fields'), list):
                        field_names = [f.get('name', '')
                                       for f in form['fields'] if f.get('name')]
                    elif isinstance(form.get('fields'), str):
                        try:
                            field_list = eval(form.get('fields', '[]'))
                            field_names = [f.get('name', '')
                                           for f in field_list if f.get('name')]
                        except:
                            pass

                    if field_names:
                        field_names_display = ', '.join(field_names[:5])
                        if len(field_names) > 5:
                            field_names_display += f" + {len(field_names) - 5} more"
                        self.addPreviewRow(
                            f"    └─ Fields", field_names_display)

            # Add form summary statistics
            if len(forms) > 5:
                self.addPreviewRow(
                    f"  ... and {len(forms) - 5} more forms", "")

            self.addPreviewRow("📊 Total Form Fields", str(total_form_fields))
            self.addPreviewRow("🎯 Forms with Actions", str(forms_with_action))
            self.addPreviewRow("🏷️ Forms with Names/IDs",
                               str(forms_with_names))

        # Add CSS and styling information
        self.addPreviewRow("═══ CSS & STYLING INFO ═══", "")

        # Count meta tags
        meta_count = sum(1 for key in page_details.keys()
                         if key.startswith("meta_"))
        self.addPreviewRow("🏷️ Meta Tags", str(meta_count))

        # Add enhanced detection success rate
        total_fields = page_details.get("total_fields", 0)
        named_fields = page_details.get("named_fields", 0)
        id_fields = page_details.get("id_fields", 0)

        if total_fields > 0:
            identifiable_fields = named_fields + id_fields
            success_rate = round((identifiable_fields / total_fields) * 100, 1)
            self.addPreviewRow("🎯 Field Identification Rate",
                               f"{success_rate}% ({identifiable_fields}/{total_fields})")

        # Add standalone fields info
        standalone_fields = page_details.get("standalone_fields", [])
        if isinstance(standalone_fields, str):
            try:
                standalone_fields = eval(standalone_fields)
            except:
                standalone_fields = []

        if standalone_fields:
            self.addPreviewRow("🔗 Standalone Fields",
                               str(len(standalone_fields)))

        # Add actions/buttons info
        actions_count = page_details.get(
            "actions_count", 0) or field_summary.get("total_actions", 0)
        if actions_count > 0:
            self.addPreviewRow("🖱️ Interactive Elements", str(actions_count))

        # Add scripts information
        scripts = page_details.get("scripts", [])
        if isinstance(scripts, str):
            try:
                scripts = eval(scripts)
            except:
                scripts = []

        if scripts:
            self.addPreviewRow("⚡ JavaScript Scripts", str(len(scripts)))

        # Add session information
        session_id = page_details.get("session_id", "")
        if session_id:
            self.addPreviewRow(
                "🏷️ Session ID", session_id[:8] + "..." if len(session_id) > 8 else session_id)

    def addPreviewRow(self, property_name, value):
        """Helper to add a row to the preview table"""
        row = self.page_preview.rowCount()
        self.page_preview.insertRow(row)
        self.page_preview.setItem(row, 0, QTableWidgetItem(property_name))
        self.page_preview.setItem(row, 1, QTableWidgetItem(value))

    def viewFullDetails(self):
        """Open the full details dialog for the selected page"""
        url = self.preview_url.toPlainText()
        if url:
            self.pageSelected.emit(url)

    def exportFlowsToCSV(self):
        """Export flows to CSV file"""
        if not self.flows:
            QMessageBox.information(
                self, "No Data", "There are no flows to export.")
            return

        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"web_flows_{timestamp}.csv"

        # Ask user for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Flows CSV", default_filename, "CSV Files (*.csv)"
        )

        if not file_path:
            return  # User canceled

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                # Create CSV writer
                writer = csv.writer(csvfile)

                # Write header
                writer.writerow(["Flow ID", "Step", "From URL",
                                "From Title", "To URL", "To Title", "Is Alert"])

                # Write data for each flow
                for flow_index, flow_path in enumerate(self.flows):
                    flow_id = f"Flow {flow_index + 1}"

                    for step_index, step in enumerate(flow_path):
                        writer.writerow([
                            flow_id,
                            f"Step {step_index + 1}",
                            step.get('from_url', ''),
                            step.get('from_title', 'Unknown'),
                            step.get('to_url', ''),
                            step.get('to_title', 'Unknown'),
                            "Yes" if step.get('is_alert', False) else "No"
                        ])

            QMessageBox.information(
                self, "Export Successful", f"Flows exported to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Error exporting flows: {str(e)}")
