from PyQt5.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout, 
                           QHBoxLayout, QTabWidget, QWidget, QTextEdit,
                           QTableWidget, QTableWidgetItem, QTreeWidget,
                           QTreeWidgetItem, QHeaderView, QScrollArea,
                           QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import csv
import os

from database.graph_db import get_page_details
from database.vector_db import get_page_content, find_similar_pages

class PageDetailsDialog(QDialog):
    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.parent = parent
        self.captured_forms = []  # To store form data for CSV export
        self.initUI()
        self.loadData()
        
    def initUI(self):
        self.setWindowTitle(f"Page Details")
        
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
            self.setGeometry(100, 100, 800, 600)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Create scroll area for the entire content
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_container = QWidget()
        main_scroll_layout = QVBoxLayout(main_container)
        
        # Top section - Basic info
        top_layout = QHBoxLayout()
        
        self.title_label = QLabel("Loading...")
        self.title_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.title_label.setWordWrap(True)
        top_layout.addWidget(self.title_label, 1)
        
        main_scroll_layout.addLayout(top_layout)
        
        self.url_label = QLabel(self.url)
        self.url_label.setStyleSheet("color: blue; text-decoration: underline;")
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url_label.setWordWrap(True)
        main_scroll_layout.addWidget(self.url_label)
        
        # Tab widget for different aspects
        self.tab_widget = QTabWidget()
        
        # Content tab
        self.content_tab = QWidget()
        content_layout = QVBoxLayout(self.content_tab)
        
        # Content text area
        self.content_text = QTextEdit()
        self.content_text.setReadOnly(True)
        self.content_text.setMinimumHeight(300)
        content_layout.addWidget(self.content_text)
        
        self.tab_widget.addTab(self.content_tab, "Content")
        
        # Metadata tab
        self.meta_tab = QWidget()
        meta_layout = QVBoxLayout(self.meta_tab)
        
        # Metadata table
        self.meta_table = QTableWidget()
        self.meta_table.setColumnCount(2)
        self.meta_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.meta_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.meta_table.verticalHeader().setVisible(False)
        self.meta_table.setAlternatingRowColors(True)
        meta_layout.addWidget(self.meta_table)
        
        # Forms tab
        self.forms_tab = QWidget()
        forms_layout = QVBoxLayout(self.forms_tab)
        
        # Forms tree widget
        self.forms_tree = QTreeWidget()
        self.forms_tree.setHeaderLabels(["Form Details", "Value"])
        self.forms_tree.setColumnWidth(0, 300)
        self.forms_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        forms_layout.addWidget(self.forms_tree)
        
        # Add Export Forms button
        export_layout = QHBoxLayout()
        export_layout.addStretch(1)
        self.export_forms_button = QPushButton("Export Forms to CSV")
        self.export_forms_button.clicked.connect(self.exportFormsToCSV)
        export_layout.addWidget(self.export_forms_button)
        forms_layout.addLayout(export_layout)
        
        self.tab_widget.addTab(self.forms_tab, "Forms")
        
        # Similar pages tab
        self.similar_tab = QWidget()
        similar_layout = QVBoxLayout(self.similar_tab)
        
        # Similar pages table
        self.similar_table = QTableWidget()
        self.similar_table.setColumnCount(2)
        self.similar_table.setHorizontalHeaderLabels(["URL", "Similarity %"])
        self.similar_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.similar_table.verticalHeader().setVisible(False)
        self.similar_table.setAlternatingRowColors(True)
        similar_layout.addWidget(self.similar_table)
        
        self.tab_widget.addTab(self.similar_tab, "Similar Pages")
        
        # Add tab widget to the main layout
        main_scroll_layout.addWidget(self.tab_widget)
        
        # Set the main container as the widget for the scroll area
        main_scroll.setWidget(main_container)
        
        # Add the scroll area to the main layout
        layout.addWidget(main_scroll)
        
        # Buttons layout
        buttons_layout = QHBoxLayout()
        
        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.loadData)
        buttons_layout.addWidget(self.refresh_button)
        
        # Spacer
        buttons_layout.addStretch(1)
        
        # Close button
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.close_button)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
    def addFormProperty(self, parent_item, name, value):
        """Helper to add a property to a form or field item"""
        if value is not None:  # Only add if there's a value (including empty strings)
            prop_item = QTreeWidgetItem(parent_item)
            prop_item.setText(0, name)
            prop_item.setText(1, str(value))
    
    def loadData(self):
        # Get page details from Neo4j
        page_details = get_page_details(self.url)
        if not page_details:
            self.title_label.setText("Error: Page not found")
            return
            
        # Set title
        self.title_label.setText(page_details.get("title", "No Title"))
        
        # Clear the forms list
        self.captured_forms = []
        
        # Load page content from Vector DB
        content_data = get_page_content(self.url)
        if content_data:
            self.content_text.setText(content_data.get("content", "No content available"))
            self.tab_widget.setTabText(0, f"Content (Captured: {content_data.get('datetime', 'Unknown')})")
        else:
            self.content_text.setText("No content available")
        
        # Populate metadata
        self.meta_table.setRowCount(0)  # Clear existing rows
        row = 0
        for key, value in page_details.items():
            if key not in ["forms", "standalone_fields", "scripts"] and not key.startswith("meta_"):
                self.meta_table.insertRow(row)
                self.meta_table.setItem(row, 0, QTableWidgetItem(key))
                
                # Format value for display
                value_str = str(value)
                if len(value_str) > 1000:  # Truncate very long values
                    value_str = value_str[:1000] + "..."
                
                self.meta_table.setItem(row, 1, QTableWidgetItem(value_str))
                row += 1
        
        # Add meta tags
        for key, value in page_details.items():
            if key.startswith("meta_"):
                self.meta_table.insertRow(row)
                self.meta_table.setItem(row, 0, QTableWidgetItem(key.replace("meta_", "meta:")))
                
                # Format value for display
                value_str = str(value)
                if len(value_str) > 1000:  # Truncate very long values
                    value_str = value_str[:1000] + "..."
                    
                self.meta_table.setItem(row, 1, QTableWidgetItem(value_str))
                row += 1
        
        # Populate forms
        self.forms_tree.clear()
        form_count = 0
        
        for form in page_details.get("forms", []):
            if not form:
                continue
                
            form_count += 1
            form_item = QTreeWidgetItem(self.forms_tree)
            form_name = form.get("form_name", "") or form.get("form_id", "") or f"Form {form_count}"
            form_item.setText(0, form_name)
            form_item.setText(1, form.get("id", "Unknown"))
            
            # Create form data for CSV export
            form_data = {
                "form_name": form_name,
                "form_id": form.get("form_id", ""),
                "action": form.get("action", ""),
                "method": form.get("method", ""),
                "fields": []
            }
            
            # Form properties
            properties_item = QTreeWidgetItem(form_item)
            properties_item.setText(0, "Properties")
            properties_item.setText(1, "")
            
            # Add form properties
            self.addFormProperty(properties_item, "Action", form.get("action", ""))
            self.addFormProperty(properties_item, "Method", form.get("method", ""))
            self.addFormProperty(properties_item, "ID", form.get("form_id", ""))
            self.addFormProperty(properties_item, "Name", form.get("form_name", ""))
            self.addFormProperty(properties_item, "Class", form.get("form_class", ""))
            self.addFormProperty(properties_item, "Enctype", form.get("enctype", ""))
            self.addFormProperty(properties_item, "Target", form.get("target", ""))
            self.addFormProperty(properties_item, "Field Count", str(form.get("field_count", 0)))
            
            # Add field names as comma-separated values right after the count
            field_names_item = QTreeWidgetItem(properties_item)
            field_names_item.setText(0, "Field Names (CSV)")
            field_names_csv = ""  # Will be populated as we process fields
            
            # Initialize field_names before any conditions
            field_names = []
            
            # Add fields section
            fields_found = False
            
            # Process fields if they exist in the Neo4j response
            if "HAS_FIELD" in form:
                fields_found = True
                fields_item = QTreeWidgetItem(form_item)
                fields_item.setText(0, "Fields")
                fields_item.setText(1, f"{len(form['HAS_FIELD'])} fields")
                
                # Collect field names for CSV display
                field_names = []
                
                for field_relationship in form.get("HAS_FIELD", []):
                    if field_relationship and "end" in field_relationship:
                        field = field_relationship["end"]
                        field_item = QTreeWidgetItem(fields_item)
                        field_name = field.get("name", "") or "Field " + str(field.get("field_index", ""))
                        field_item.setText(0, field_name)
                        field_item.setText(1, field.get("type", "unknown"))
                        
                        # Add field name to our list if it's not empty
                        if field_name and field_name != "Field ":
                            field_names.append(field_name)
                        
                        # Add to form_data for CSV export
                        form_data["fields"].append({
                            "name": field_name,
                            "type": field.get("type", ""),
                            "id": field.get("field_id", ""),
                            "required": field.get("required", False)
                        })
                        
                        # Add field properties
                        self.addFormProperty(field_item, "Type", field.get("type", ""))
                        self.addFormProperty(field_item, "ID", field.get("field_id", ""))
                        self.addFormProperty(field_item, "Name", field.get("name", ""))
                        self.addFormProperty(field_item, "Placeholder", field.get("placeholder", ""))
                        self.addFormProperty(field_item, "Value", field.get("value", ""))
                        self.addFormProperty(field_item, "Required", "Yes" if field.get("required", False) else "No")
                        
                        # Add select options
                        if field.get("type") == "select" and "HAS_OPTION" in field:
                            options_item = QTreeWidgetItem(field_item)
                            options_item.setText(0, "Options")
                            options_item.setText(1, f"{len(field['HAS_OPTION'])} options")
                            
                            # Store options for CSV
                            options = []
                            
                            for option_rel in field.get("HAS_OPTION", []):
                                if option_rel and "end" in option_rel:
                                    option = option_rel["end"]
                                    option_item = QTreeWidgetItem(options_item)
                                    option_item.setText(0, option.get("text", "") or option.get("value", ""))
                                    option_item.setText(1, "Selected" if option.get("selected", False) else "")
                                    
                                    # Add to options list
                                    options.append(option.get("text", "") or option.get("value", ""))
                            
                            # Add options to field data
                            form_data["fields"][-1]["options"] = options
            
            # Try to parse fields from serialized string if not found as relationships
            if not fields_found:
                fields_str = form.get("fields", "[]")
                try:
                    fields = eval(fields_str)  # Convert string representation to list
                    
                    if fields:
                        fields_item = QTreeWidgetItem(form_item)
                        fields_item.setText(0, "Fields")
                        fields_item.setText(1, f"{len(fields)} fields")
                        
                        # Collect field names for CSV display
                        field_names = []
                        
                        for i, field in enumerate(fields):
                            field_item = QTreeWidgetItem(fields_item)
                            field_name = field.get("name", "") or f"Field {i+1}"
                            field_type = field.get("type", "unknown")
                            field_item.setText(0, field_name)
                            field_item.setText(1, field_type)
                            
                            # Add field name to our list if it's not empty or auto-generated
                            if field_name and not field_name.startswith("Field "):
                                field_names.append(field_name)
                            
                            # Add to form_data for CSV export
                            form_data["fields"].append({
                                "name": field_name,
                                "type": field_type,
                                "id": field.get("id", ""),
                                "required": field.get("required", False)
                            })
                            
                            # Add field details
                            for key, value in field.items():
                                if key not in ["name", "type"]:
                                    detail_item = QTreeWidgetItem(field_item)
                                    detail_item.setText(0, key.capitalize())
                                    detail_item.setText(1, str(value))
                                    
                            # Process options for select fields
                            if field_type == "select" and "options" in field:
                                options = field.get("options", [])
                                if options:
                                    options_item = QTreeWidgetItem(field_item)
                                    options_item.setText(0, "Options")
                                    options_item.setText(1, f"{len(options)} options")
                                    
                                    # Store options for CSV
                                    option_values = []
                                    
                                    for j, option in enumerate(options):
                                        option_item = QTreeWidgetItem(options_item)
                                        option_text = option.get("text", "") or option.get("value", "")
                                        option_item.setText(0, option_text)
                                        option_item.setText(1, "Selected" if option.get("selected", False) else "")
                                        
                                        # Add to options list
                                        option_values.append(option_text)
                                    
                                    # Add options to field data
                                    form_data["fields"][-1]["options"] = option_values
                except Exception as e:
                    # Fallback if parsing fails
                    fields_item = QTreeWidgetItem(form_item)
                    fields_item.setText(0, "Fields (Raw)")
                    fields_item.setText(1, f"Error parsing fields: {str(e)}")
                    
                    raw_item = QTreeWidgetItem(fields_item)
                    raw_text = fields_str[:1000] + "..." if len(fields_str) > 1000 else fields_str
                    raw_item.setText(0, "Raw Data")
                    raw_item.setText(1, raw_text)
                    
                    # No field names in case of error
                    field_names = []
            
            # Now that we've processed all fields, update the field names CSV display
            if field_names:
                field_names_csv = ", ".join(field_names)
            else:
                field_names_csv = "No named fields found"
                
            # Set the CSV text in the field names item
            field_names_item.setText(1, field_names_csv)
            
            # Add the form data to our list
            self.captured_forms.append(form_data)
        
        # Add standalone fields section
        standalone_fields = page_details.get("standalone_fields", "[]")
        try:
            fields = eval(standalone_fields) if isinstance(standalone_fields, str) else standalone_fields
            if fields:
                standalone_item = QTreeWidgetItem(self.forms_tree)
                standalone_item.setText(0, "Standalone Fields")
                standalone_item.setText(1, f"{len(fields)} fields")
                
                # Create standalone form data for CSV export
                standalone_form = {
                    "form_name": "Standalone Fields",
                    "form_id": "",
                    "action": "",
                    "method": "",
                    "fields": []
                }
                
                # Add a property for field names as CSV
                field_names_item = QTreeWidgetItem(standalone_item)
                field_names_item.setText(0, "Field Names (CSV)")
                
                # Collect field names
                standalone_field_names = []
                
                for i, field in enumerate(fields):
                    field_item = QTreeWidgetItem(standalone_item)
                    field_name = field.get("name", "") or f"Field {i+1}"
                    field_type = field.get("type", "unknown")
                    field_item.setText(0, field_name)
                    field_item.setText(1, field_type)
                    
                    # Add field name to our list if it's not empty or auto-generated
                    if field_name and not field_name.startswith("Field "):
                        standalone_field_names.append(field_name)
                    
                    # Add to standalone form data
                    standalone_form["fields"].append({
                        "name": field_name,
                        "type": field_type,
                        "id": field.get("id", ""),
                        "required": False
                    })
                    
                    # Add field details
                    for key, value in field.items():
                        if key not in ["name", "type"]:
                            detail_item = QTreeWidgetItem(field_item)
                            detail_item.setText(0, key.capitalize())
                            detail_item.setText(1, str(value))
                
                # Set the CSV text in the field names item
                if standalone_field_names:
                    field_names_item.setText(1, ", ".join(standalone_field_names))
                else:
                    field_names_item.setText(1, "No named fields found")
                
                # Add standalone fields to our list if there are any
                if standalone_form["fields"]:
                    self.captured_forms.append(standalone_form)
        except Exception as e:
            print(f"Error processing standalone fields: {e}")
        
        # Add scripts section
        scripts = page_details.get("scripts", "[]")
        try:
            script_list = eval(scripts) if isinstance(scripts, str) else scripts
            if script_list:
                scripts_item = QTreeWidgetItem(self.forms_tree)
                scripts_item.setText(0, "Scripts")
                scripts_item.setText(1, f"{len(script_list)} scripts")
                
                for i, script in enumerate(script_list):
                    script_item = QTreeWidgetItem(scripts_item)
                    script_item.setText(0, f"Script {i+1}")
                    script_item.setText(1, script.get("type", ""))
                    
                    # Add script details
                    for key, value in script.items():
                        if key != "type":
                            detail_item = QTreeWidgetItem(script_item)
                            detail_item.setText(0, key.capitalize())
                            detail_item.setText(1, str(value))
        except Exception as e:
            print(f"Error processing scripts: {e}")
        
        self.forms_tree.expandAll()
        
        # Find similar pages
        session_id = page_details.get("session_id", None)
        similar_pages = find_similar_pages(self.url, session_id=session_id)
        
        self.similar_table.setRowCount(len(similar_pages))
        for row, page in enumerate(similar_pages):
            url_item = QTableWidgetItem(page.get("url", ""))
            url_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.similar_table.setItem(row, 0, url_item)
            
            similarity_item = QTableWidgetItem(f"{page.get('similarity', 0)}%")
            similarity_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.similar_table.setItem(row, 1, similarity_item)
        
        # Enable/disable export button based on whether we have any forms
        self.export_forms_button.setEnabled(len(self.captured_forms) > 0)
    
    def exportFormsToCSV(self):
        """Export form field names to CSV"""
        if not self.captured_forms:
            QMessageBox.information(self, "No Forms", "No forms available to export.")
            return
        
        # Ask user for save location
        default_filename = f"form_fields_{int(time.time())}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Forms CSV", default_filename, "CSV Files (*.csv)"
        )
        
        if not file_path:
            return  # User canceled
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                # Create CSV writer
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(["Form Name", "Form ID", "Action", "Method", "Field Names"])
                
                # Write data for each form
                for form in self.captured_forms:
                    # Gather all field names in a comma-separated string
                    field_names = []
                    for field in form.get("fields", []):
                        field_name = field.get("name", "")
                        if field_name:
                            field_names.append(field_name)
                    
                    # Write the row
                    writer.writerow([
                        form.get("form_name", ""),
                        form.get("form_id", ""),
                        form.get("action", ""),
                        form.get("method", ""),
                        ", ".join(field_names)
                    ])
                
                # Write a more detailed section with all field data
                writer.writerow([])  # Empty row for separation
                writer.writerow(["DETAILED FIELD INFORMATION"])
                writer.writerow(["Form Name", "Form ID", "Field Name", "Field Type", "Field ID", "Required"])
                
                for form in self.captured_forms:
                    form_name = form.get("form_name", "")
                    form_id = form.get("form_id", "")
                    
                    for field in form.get("fields", []):
                        writer.writerow([
                            form_name,
                            form_id,
                            field.get("name", ""),
                            field.get("type", ""),
                            field.get("id", ""),
                            "Yes" if field.get("required", False) else "No"
                        ])
            
            QMessageBox.information(self, "Export Successful", f"Forms exported to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error exporting forms: {str(e)}")

# For testing the export functionality
import time