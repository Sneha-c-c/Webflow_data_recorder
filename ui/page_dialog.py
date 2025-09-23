import time
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
            self.setGeometry(0, 0, int(parent_width * 0.9),
                             int(parent_height * 0.9))
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
        self.url_label.setStyleSheet(
            "color: blue; text-decoration: underline;")
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

        self.tab_widget.addTab(self.meta_tab, "Metadata")

        # Field Statistics tab
        self.stats_tab = QWidget()
        stats_layout = QVBoxLayout(self.stats_tab)

        # Field statistics table
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setAlternatingRowColors(True)
        stats_layout.addWidget(self.stats_table)

        self.tab_widget.addTab(self.stats_tab, "Field Statistics")

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
            self.content_text.setText(content_data.get(
                "content", "No content available"))
            self.tab_widget.setTabText(
                0, f"Content (Captured: {content_data.get('datetime', 'Unknown')})")
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

        # Populate field statistics
        self.populateFieldStatistics(page_details)

        # Add meta tags
        for key, value in page_details.items():
            if key.startswith("meta_"):
                self.meta_table.insertRow(row)
                self.meta_table.setItem(row, 0, QTableWidgetItem(
                    key.replace("meta_", "meta:")))

                # Format value for display
                value_str = str(value)
                if len(value_str) > 1000:  # Truncate very long values
                    value_str = value_str[:1000] + "..."

                self.meta_table.setItem(row, 1, QTableWidgetItem(value_str))
                row += 1

        # Enhanced Forms Processing
        self.forms_tree.clear()
        form_count = 0

        # Process Neo4j forms with relationships
        for form in page_details.get("forms", []):
            if not form:
                continue

            form_count += 1
            form_item = QTreeWidgetItem(self.forms_tree)

            # Debug form data structure
            self.debug_form_data(form, form_count)

            # Enhanced form identification
            form_name = self._get_best_form_identifier(form, form_count)
            form_item.setText(0, form_name)
            form_item.setText(1, f"Form {form_count}")

            # Create enhanced form data for CSV export
            form_data = {
                "form_name": form_name,
                "form_id": form.get("form_id", "") or form.get("id", ""),
                "action": form.get("action", ""),
                "method": form.get("method", ""),
                "fields": []
            }

            # Form properties with enhanced display
            properties_item = QTreeWidgetItem(form_item)
            properties_item.setText(0, "📋 Form Properties")
            properties_item.setText(1, "")

            # Add comprehensive form properties
            self.addFormProperty(properties_item, "🎯 Action", form.get(
                "action", "") or "No action specified")
            self.addFormProperty(properties_item, "📤 Method",
                                 (form.get("method", "GET") or "GET").upper())
            self.addFormProperty(properties_item, "🆔 Form ID", form.get(
                "form_id", "") or form.get("id", "") or "No ID")
            self.addFormProperty(properties_item, "🏷️ Form Name", form.get(
                "form_name", "") or form.get("name", "") or "No name")
            self.addFormProperty(properties_item, "🎨 CSS Classes", form.get(
                "form_class", "") or form.get("class", "") or "No classes")
            self.addFormProperty(properties_item, "📄 Encoding", form.get(
                "enctype", "") or "application/x-www-form-urlencoded")
            self.addFormProperty(properties_item, "🎯 Target",
                                 form.get("target", "") or "_self")
            self.addFormProperty(properties_item, "🔢 Total Fields", str(
                form.get("field_count", 0)))

            # Enhanced field processing with multiple data source attempts
            fields_found = False
            field_names = []  # Will collect all identifiable field names

            print(f"🔍 Processing fields for form: {form_name}")
            print(f"🔍 Available form keys: {list(form.keys())}")

            # ATTEMPT 1: Try to get fields from Neo4j relationships (HAS_FIELD)
            if "HAS_FIELD" in form and form["HAS_FIELD"]:
                print(
                    f"✅ Found HAS_FIELD relationships: {len(form['HAS_FIELD'])}")
                fields_found = True
                fields_item = QTreeWidgetItem(form_item)
                fields_item.setText(0, "🔍 Form Fields (Neo4j)")
                fields_item.setText(
                    1, f"{len(form['HAS_FIELD'])} fields detected")

                for field_idx, field_relationship in enumerate(form.get("HAS_FIELD", [])):
                    if field_relationship and "end" in field_relationship:
                        field = field_relationship["end"]
                        print(
                            f"🔍 Processing field {field_idx}: {list(field.keys())}")

                        # Enhanced field identification
                        field_identifier = self._get_best_field_identifier(
                            field)
                        field_type = field.get("type", "unknown")

                        field_item = QTreeWidgetItem(fields_item)
                        field_item.setText(0, f"🔘 {field_identifier}")
                        field_item.setText(1, field_type)

                        # Add to field names list if identifiable
                        if field_identifier and not field_identifier.startswith("field_"):
                            field_names.append(field_identifier)

                        # Add to form_data for CSV export
                        form_data["fields"].append({
                            "identifier": field_identifier,
                            "name": field.get("name", ""),
                            "id": field.get("field_id", "") or field.get("id", ""),
                            "type": field_type,
                            "required": field.get("required", False),
                            "placeholder": field.get("placeholder", ""),
                            "aria_label": field.get("aria_label", ""),
                            "class": field.get("class", ""),
                            "value": field.get("value", "")
                        })

                        # Enhanced field properties display
                        self._add_comprehensive_field_properties(
                            field_item, field)

            # ATTEMPT 2: Try to parse from serialized fields string
            elif "fields" in form and form.get("fields"):
                fields_str = form.get("fields", "")
                print(
                    f"🔍 Trying to parse serialized fields: {fields_str[:100]}...")

                try:
                    if isinstance(fields_str, str) and fields_str.strip():
                        # Handle different string formats
                        if fields_str.startswith('[') and fields_str.endswith(']'):
                            fields = eval(fields_str)  # Parse list string
                        elif fields_str.startswith('{'):
                            # Single dict as string
                            fields = [eval(fields_str)]
                        else:
                            # Try to parse as Python literal
                            import ast
                            fields = ast.literal_eval(fields_str)
                    elif isinstance(fields_str, list):
                        fields = fields_str
                    elif isinstance(fields_str, dict):
                        fields = [fields_str]
                    else:
                        fields = []

                    print(
                        f"✅ Parsed {len(fields)} fields from serialized data")

                    if fields:
                        fields_found = True
                        fields_item = QTreeWidgetItem(form_item)
                        fields_item.setText(0, "🔍 Form Fields (Parsed)")
                        fields_item.setText(
                            1, f"{len(fields)} fields detected")

                        for i, field in enumerate(fields):
                            print(
                                f"🔍 Processing parsed field {i}: {list(field.keys()) if isinstance(field, dict) else str(field)}")

                            # Enhanced field identification
                            field_identifier = self._get_best_field_identifier(
                                field, i)
                            field_type = field.get("type", "unknown") if isinstance(
                                field, dict) else "unknown"

                            field_item = QTreeWidgetItem(fields_item)
                            field_item.setText(0, f"🔘 {field_identifier}")
                            field_item.setText(1, field_type)

                            # Add to field names list if identifiable
                            if field_identifier and not field_identifier.startswith("field_"):
                                field_names.append(field_identifier)

                            # Add to form_data for CSV export
                            if isinstance(field, dict):
                                form_data["fields"].append({
                                    "identifier": field_identifier,
                                    "name": field.get("name", ""),
                                    "id": field.get("id", ""),
                                    "type": field_type,
                                    "required": field.get("required", False),
                                    "placeholder": field.get("placeholder", ""),
                                    "aria_label": field.get("aria_label", ""),
                                    "class": field.get("class", ""),
                                    "value": field.get("value", "")
                                })

                                # Enhanced field properties display
                                self._add_comprehensive_field_properties(
                                    field_item, field)
                            else:
                                # Handle non-dict field data
                                form_data["fields"].append({
                                    "identifier": field_identifier,
                                    "name": "",
                                    "id": "",
                                    "type": str(field),
                                    "required": False,
                                    "placeholder": "",
                                    "aria_label": "",
                                    "class": "",
                                    "value": ""
                                })

                except Exception as e:
                    print(f"❌ Error parsing serialized fields: {e}")
                    # Show parsing error in UI
                    fields_item = QTreeWidgetItem(form_item)
                    fields_item.setText(0, "⚠️ Field Parsing Error")
                    fields_item.setText(1, f"Error: {str(e)[:50]}...")

                    error_detail = QTreeWidgetItem(fields_item)
                    error_detail.setText(0, "Raw Data")
                    error_detail.setText(
                        1, fields_str[:200] + "..." if len(fields_str) > 200 else fields_str)

            # ATTEMPT 3: Try to get field_count and generate placeholder info
            elif "field_count" in form and form.get("field_count", 0) > 0:
                field_count = form.get("field_count", 0)
                print(
                    f"🔍 No field details found, but field_count = {field_count}")

                fields_item = QTreeWidgetItem(form_item)
                fields_item.setText(0, f"⚠️ {field_count} Fields Detected")
                fields_item.setText(1, "Details not available")

                # Add explanation
                explanation_item = QTreeWidgetItem(fields_item)
                explanation_item.setText(0, "Status")
                explanation_item.setText(
                    1, "Fields detected but details not captured properly")

                # Add suggestions
                suggestion_item = QTreeWidgetItem(fields_item)
                suggestion_item.setText(0, "Suggestion")
                suggestion_item.setText(
                    1, "Try re-capturing with enhanced Selenium detection")

            # ATTEMPT 4: Check for direct field properties in form data
            else:
                print(f"🔍 Checking for direct field properties in form data...")

                # Look for individual field properties that might be stored directly
                direct_fields = []
                for key, value in form.items():
                    if key.startswith("field_") or "input" in key.lower() or "button" in key.lower():
                        print(
                            f"🔍 Found potential field property: {key} = {value}")
                        direct_fields.append({"property": key, "value": value})

                if direct_fields:
                    fields_found = True
                    fields_item = QTreeWidgetItem(form_item)
                    fields_item.setText(0, "🔍 Field Properties (Direct)")
                    fields_item.setText(
                        1, f"{len(direct_fields)} properties found")

                    for prop in direct_fields:
                        prop_item = QTreeWidgetItem(fields_item)
                        prop_item.setText(0, prop["property"])
                        prop_item.setText(1, str(prop["value"])[:100])

            # If still no fields found, create informative placeholder
            if not fields_found:
                print(f"❌ No fields found for form using any method")
                fields_item = QTreeWidgetItem(form_item)
                fields_item.setText(0, "❌ No Field Data Available")
                fields_item.setText(
                    1, "Fields may be dynamically generated or not properly captured")

                # Add debugging info
                debug_item = QTreeWidgetItem(fields_item)
                debug_item.setText(0, "Debug Info")
                debug_item.setText(
                    1, f"Form has keys: {', '.join(form.keys())}")

            # Enhanced field names summary with comprehensive identification
            field_names_item = QTreeWidgetItem(properties_item)
            field_names_item.setText(0, "📝 Identifiable Fields")

            if field_names:
                # Show actual field names found
                field_names_csv = ", ".join(field_names)
                if len(field_names_csv) > 100:
                    field_names_csv = field_names_csv[:100] + \
                        f"... ({len(field_names)} total)"
                field_names_item.setText(1, field_names_csv)
                print(
                    f"✅ Found {len(field_names)} identifiable fields: {field_names}")
            else:
                # Show why no fields were identified
                if fields_found:
                    field_names_item.setText(
                        1, "⚠️ Fields found but lack identifying attributes (name/id/aria-label)")
                else:
                    field_names_item.setText(
                        1, "❌ No field data captured - may need enhanced detection")
                print(f"❌ No identifiable fields found")

            # Add field identification breakdown
            if field_names:
                breakdown_item = QTreeWidgetItem(field_names_item)
                breakdown_item.setText(0, "Identification Methods Used")

                # Analyze what identification methods were successful
                methods_used = []
                for field in form_data["fields"]:
                    if field.get("name"):
                        methods_used.append("name")
                    elif field.get("id"):
                        methods_used.append("id")
                    elif field.get("aria_label"):
                        methods_used.append("aria-label")
                    elif field.get("placeholder"):
                        methods_used.append("placeholder")

                unique_methods = list(set(methods_used))
                breakdown_item.setText(1, ", ".join(
                    unique_methods) if unique_methods else "none")

            # Add the form data to our export list
            self.captured_forms.append(form_data)

        # Enhanced standalone fields processing
        standalone_fields = page_details.get("standalone_fields", "[]")
        try:
            fields = eval(standalone_fields) if isinstance(
                standalone_fields, str) else standalone_fields
            if fields:
                standalone_item = QTreeWidgetItem(self.forms_tree)
                standalone_item.setText(0, "🔗 Standalone Elements")
                standalone_item.setText(
                    1, f"{len(fields)} elements outside forms")

                # Create standalone form data for CSV export
                standalone_form = {
                    "form_name": "Standalone Elements",
                    "form_id": "",
                    "action": "",
                    "method": "",
                    "fields": []
                }

                # Enhanced standalone field names
                standalone_field_names = []

                for i, field in enumerate(fields):
                    field_identifier = self._get_best_field_identifier(
                        field, i)
                    field_type = field.get("type", "unknown")

                    field_item = QTreeWidgetItem(standalone_item)
                    field_item.setText(0, f"🔘 {field_identifier}")
                    field_item.setText(1, field_type)

                    # Add to field names list if identifiable
                    if field_identifier and not field_identifier.startswith("field_"):
                        standalone_field_names.append(field_identifier)

                    # Add to standalone form data
                    standalone_form["fields"].append({
                        "identifier": field_identifier,
                        "name": field.get("name", ""),
                        "id": field.get("id", ""),
                        "type": field_type,
                        "required": field.get("required", False),
                        "placeholder": field.get("placeholder", ""),
                        "aria_label": field.get("aria_label", ""),
                        "class": field.get("class", ""),
                        "value": field.get("value", "")
                    })

                    # Enhanced field properties display
                    self._add_comprehensive_field_properties(field_item, field)

                # Add field names summary
                field_names_item = QTreeWidgetItem(standalone_item)
                field_names_item.setText(0, "📝 Identifiable Elements")

                if standalone_field_names:
                    field_names_item.setText(
                        1, ", ".join(standalone_field_names))
                else:
                    field_names_item.setText(1, "⚠️ No identifiable elements")

                # Add standalone fields to our list if there are any
                if standalone_form["fields"]:
                    self.captured_forms.append(standalone_form)

        except Exception as e:
            print(f"Error processing standalone fields: {e}")

        # Enhanced scripts section
        scripts = page_details.get("scripts", "[]")
        try:
            script_list = eval(scripts) if isinstance(
                scripts, str) else scripts
            if script_list:
                scripts_item = QTreeWidgetItem(self.forms_tree)
                scripts_item.setText(0, "⚡ JavaScript Scripts")
                scripts_item.setText(1, f"{len(script_list)} scripts detected")

                for i, script in enumerate(script_list):
                    script_item = QTreeWidgetItem(scripts_item)
                    script_item.setText(0, f"📜 Script {i+1}")

                    script_type = script.get("type", "unknown")
                    if script.get("src"):
                        script_item.setText(1, f"External ({script_type})")
                        self.addFormProperty(
                            script_item, "📄 Source", script.get("src", ""))
                    elif script.get("inline"):
                        script_item.setText(1, f"Inline ({script_type})")
                        inline_preview = script.get("inline", "")[:100]
                        if len(script.get("inline", "")) > 100:
                            inline_preview += "..."
                        self.addFormProperty(
                            script_item, "💻 Code Preview", inline_preview)

                    if script.get("type"):
                        self.addFormProperty(
                            script_item, "🏷️ Type", script.get("type", ""))

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

    def populateFieldStatistics(self, page_details):
        """Populate the field statistics tab with comprehensive field information"""
        # Clear existing statistics
        self.stats_table.setRowCount(0)

        # Add comprehensive field detection summary
        self.addStatsRow("═══ FIELD DETECTION OVERVIEW ═══", "")
        self.addStatsRow("🔢 Total Fields Detected", str(
            page_details.get("total_fields", 0)))
        self.addStatsRow("🏷️ Named Fields", str(
            page_details.get("named_fields", 0)))
        self.addStatsRow("🆔 ID-based Fields",
                         str(page_details.get("id_fields", 0)))
        self.addStatsRow("💬 Placeholder Fields", str(
            page_details.get("placeholder_fields", 0)))
        self.addStatsRow("⚠️ Required Fields", str(
            page_details.get("required_fields", 0)))
        self.addStatsRow("♿ ARIA Labeled Fields", str(
            page_details.get("aria_labeled_fields", 0)))

        # Calculate and show field identification success rate
        total_fields = page_details.get("total_fields", 0)
        named_fields = page_details.get("named_fields", 0)
        id_fields = page_details.get("id_fields", 0)

        if total_fields > 0:
            identifiable_fields = named_fields + id_fields
            success_rate = round((identifiable_fields / total_fields) * 100, 1)
            self.addStatsRow("🎯 Field Identification Success",
                             f"{success_rate}% ({identifiable_fields}/{total_fields} identifiable)")

            # Add quality metrics
            if named_fields > 0:
                name_quality = round((named_fields / total_fields) * 100, 1)
                self.addStatsRow("  └─ Name Quality",
                                 f"{name_quality}% have meaningful names")

            if id_fields > 0:
                id_quality = round((id_fields / total_fields) * 100, 1)
                self.addStatsRow("  └─ ID Quality",
                                 f"{id_quality}% have unique IDs")

        # Add enhanced field statistics
        field_summary = page_details.get("field_summary", {})
        class_fields = field_summary.get("class_fields", 0)
        data_fields = field_summary.get("data_attribute_fields", 0)

        if class_fields > 0 or data_fields > 0:
            self.addStatsRow("═══ ADVANCED ATTRIBUTES ═══", "")
            if class_fields > 0:
                self.addStatsRow("🎨 Class-based Fields", str(class_fields))
            if data_fields > 0:
                self.addStatsRow("📊 Data Attribute Fields", str(data_fields))

        # Add input type breakdown with icons and descriptions
        input_types = field_summary.get("input_types", {})
        if input_types:
            self.addStatsRow("═══ INPUT TYPE BREAKDOWN ═══", "")

            # Group input types by category
            text_types = ["text", "email", "password", "search", "url", "tel"]
            choice_types = ["checkbox", "radio", "select"]
            number_types = ["number", "range"]
            date_types = ["date", "datetime",
                          "datetime-local", "time", "month", "week"]
            file_types = ["file", "image"]
            button_types = ["button", "submit", "reset"]

            for input_type, count in sorted(input_types.items()):
                # Assign icons based on type
                if input_type in text_types:
                    icon = "🔤"
                    category = "Text Input"
                elif input_type in choice_types:
                    icon = "☑️"
                    category = "Selection"
                elif input_type in number_types:
                    icon = "🔢"
                    category = "Numeric"
                elif input_type in date_types:
                    icon = "📅"
                    category = "Date/Time"
                elif input_type in file_types:
                    icon = "📎"
                    category = "File"
                elif input_type in button_types:
                    icon = "🔘"
                    category = "Button"
                else:
                    icon = "❓"
                    category = "Other"

                self.addStatsRow(
                    f"  {icon} {input_type.capitalize()}", f"{count} fields ({category})")

            # Add summary by category
            self.addStatsRow("─── Input Categories ───", "")
            text_count = sum(input_types.get(t, 0) for t in text_types)
            choice_count = sum(input_types.get(t, 0) for t in choice_types)

            if text_count > 0:
                self.addStatsRow("  📝 Text Input Fields", str(text_count))
            if choice_count > 0:
                self.addStatsRow("  ✅ Selection Fields", str(choice_count))

        # Add comprehensive form information
        forms = page_details.get("forms", [])
        self.addStatsRow("═══ FORM ANALYSIS ═══", "")
        self.addStatsRow("📝 Total Forms Found", str(len(forms)))

        if forms:
            # Analyze forms in detail
            total_form_fields = 0
            forms_with_action = 0
            forms_with_names = 0
            post_forms = 0
            get_forms = 0
            forms_with_validation = 0

            for i, form in enumerate(forms):
                # Count various form characteristics
                field_count = form.get("field_count", 0)
                total_form_fields += field_count

                if form.get("action") and form.get("action") != "":
                    forms_with_action += 1

                if form.get("form_name") or form.get("form_id"):
                    forms_with_names += 1

                method = form.get("method", "get").lower()
                if method == "post":
                    post_forms += 1
                else:
                    get_forms += 1

                # Check if form has required fields (validation)
                if form.get("required_fields", 0) > 0:
                    forms_with_validation += 1

                # Display first few forms in detail
                if i < 3:  # Show details for first 3 forms
                    form_name = form.get("form_name", "") or form.get(
                        "form_id", "") or f"Form {i+1}"
                    action = form.get("action", "No action specified")
                    method_display = form.get("method", "GET").upper()

                    self.addStatsRow(
                        f"  📋 {form_name}", f"{method_display} → {action[:50]}{'...' if len(action) > 50 else ''}")
                    self.addStatsRow(f"    └─ Field Count", str(field_count))

                    # Show enctype if not default
                    enctype = form.get("enctype", "")
                    if enctype and enctype != "application/x-www-form-urlencoded":
                        self.addStatsRow(f"    └─ Encoding", enctype)

                    # Show autocomplete setting
                    autocomplete = form.get("autocomplete", "")
                    if autocomplete:
                        self.addStatsRow(f"    └─ Autocomplete", autocomplete)

            if len(forms) > 3:
                self.addStatsRow(f"  ... and {len(forms) - 3} more forms", "")

            # Add form summary statistics
            self.addStatsRow("─── Form Summary ───", "")
            self.addStatsRow("📊 Total Form Fields", str(total_form_fields))
            self.addStatsRow("🎯 Forms with Actions",
                             f"{forms_with_action}/{len(forms)}")
            self.addStatsRow("🏷️ Forms with Names/IDs",
                             f"{forms_with_names}/{len(forms)}")

            if post_forms > 0 or get_forms > 0:
                self.addStatsRow("📤 POST Forms", str(post_forms))
                self.addStatsRow("📥 GET Forms", str(get_forms))

            if forms_with_validation > 0:
                self.addStatsRow("✅ Forms with Validation",
                                 str(forms_with_validation))

            # Calculate form complexity score
            if len(forms) > 0:
                avg_fields_per_form = total_form_fields / len(forms)
                complexity = "Simple" if avg_fields_per_form < 5 else "Moderate" if avg_fields_per_form < 15 else "Complex"
                self.addStatsRow(
                    "📈 Form Complexity", f"{complexity} ({avg_fields_per_form:.1f} fields/form avg)")

        # Add detection method and enhancement information
        self.addStatsRow("═══ DETECTION TECHNOLOGY ═══", "")
        if page_details.get("enhanced_with_selenium", False):
            self.addStatsRow("🔍 Detection Method",
                             "✅ Enhanced Multi-Method Detection")
            self.addStatsRow("  └─ HTML Parser", "BeautifulSoup")
            self.addStatsRow("  └─ Browser Automation", "Selenium WebDriver")
            self.addStatsRow("  └─ Advanced DOM", "Shadow DOM Support")

            # Show detection breakdown by method
            selenium_fields = field_summary.get("selenium_fields", 0)
            shadow_fields = field_summary.get("shadow_dom_fields", 0)

            if selenium_fields > 0:
                self.addStatsRow("  🤖 Selenium Detected",
                                 f"{selenium_fields} fields")
            if shadow_fields > 0:
                self.addStatsRow("  🌑 Shadow DOM Detected",
                                 f"{shadow_fields} fields")

            detection_coverage = "Comprehensive"
        else:
            self.addStatsRow("🔍 Detection Method",
                             "⚠️ Basic HTML Parsing Only")
            self.addStatsRow("  └─ Parser", "BeautifulSoup")
            self.addStatsRow("  ❌ Missing", "Dynamic content detection")
            detection_coverage = "Limited"

        self.addStatsRow("📊 Detection Coverage", detection_coverage)

        # Add standalone elements information
        standalone_fields = page_details.get("standalone_fields", [])
        if isinstance(standalone_fields, str):
            try:
                standalone_fields = eval(standalone_fields)
            except:
                standalone_fields = []

        if standalone_fields:
            self.addStatsRow("═══ STANDALONE ELEMENTS ═══", "")
            self.addStatsRow("🔗 Standalone Fields",
                             f"{len(standalone_fields)} fields outside forms")

        # Add scripts and dynamic content information
        scripts = page_details.get("scripts", [])
        if isinstance(scripts, str):
            try:
                scripts = eval(scripts)
            except:
                scripts = []

        if scripts:
            self.addStatsRow("═══ DYNAMIC CONTENT ═══", "")
            self.addStatsRow("⚡ JavaScript Scripts", str(len(scripts)))

            # Analyze script types
            inline_scripts = sum(1 for s in scripts if 'inline' in s)
            external_scripts = sum(1 for s in scripts if 'src' in s)

            if inline_scripts > 0:
                self.addStatsRow("  └─ Inline Scripts", str(inline_scripts))
            if external_scripts > 0:
                self.addStatsRow("  └─ External Scripts",
                                 str(external_scripts))

        # Add accessibility assessment
        aria_fields = page_details.get("aria_labeled_fields", 0)
        if total_fields > 0:
            self.addStatsRow("═══ ACCESSIBILITY ASSESSMENT ═══", "")

            if aria_fields > 0:
                aria_percentage = round((aria_fields / total_fields) * 100, 1)
                accessibility_level = "Excellent" if aria_percentage > 80 else "Good" if aria_percentage > 50 else "Fair" if aria_percentage > 20 else "Poor"
                self.addStatsRow(
                    "♿ ARIA Coverage", f"{aria_percentage}% ({aria_fields}/{total_fields})")
                self.addStatsRow("📊 Accessibility Level", accessibility_level)
            else:
                self.addStatsRow("♿ ARIA Coverage",
                                 "0% - No ARIA labels found")
                self.addStatsRow("📊 Accessibility Level",
                                 "⚠️ Poor - Needs improvement")

            # Add recommendations
            if aria_fields == 0:
                self.addStatsRow("💡 Recommendation",
                                 "Add ARIA labels for better accessibility")
            elif aria_fields < total_fields * 0.5:
                self.addStatsRow("💡 Recommendation",
                                 "Consider adding more ARIA labels")

        # Add timing and session information
        self.addStatsRow("═══ CAPTURE INFORMATION ═══", "")

        # Add timestamp information
        timestamp = page_details.get(
            "timestamp_readable", page_details.get("timestamp", ""))
        if timestamp:
            self.addStatsRow("📅 Captured At", str(timestamp))

        # Add session information
        session_id = page_details.get("session_id", "")
        if session_id:
            self.addStatsRow(
                "🏷️ Session ID", session_id[:12] + "..." if len(session_id) > 12 else session_id)

        # Add page URL for reference
        self.addStatsRow(
            "🌐 Page URL", self.url[:60] + "..." if len(self.url) > 60 else self.url)

    def addStatsRow(self, metric, value):
        """Helper to add a row to the statistics table"""
        row = self.stats_table.rowCount()
        self.stats_table.insertRow(row)
        self.stats_table.setItem(row, 0, QTableWidgetItem(metric))
        self.stats_table.setItem(row, 1, QTableWidgetItem(value))

    def exportFormsToCSV(self):
        """Export form field data with enhanced modern field identification"""
        if not self.captured_forms:
            QMessageBox.information(
                self, "No Forms", "No forms available to export.")
            return

        # Ask user for save location
        default_filename = f"enhanced_form_fields_{int(time.time())}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Enhanced Forms CSV", default_filename, "CSV Files (*.csv)"
        )

        if not file_path:
            return  # User canceled

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                # Create CSV writer
                writer = csv.writer(csvfile)

                # Write comprehensive header
                writer.writerow([
                    "Form Name", "Form ID", "Action", "Method",
                    "Field Identifier", "Field Name", "Field ID", "Field Type",
                    "Placeholder", "ARIA Label", "CSS Classes", "Required",
                    "Has Data Attributes", "Detection Method", "Automation Selector"
                ])

                # Write enhanced data for each form
                for form in self.captured_forms:
                    form_name = form.get("form_name", "")
                    form_id = form.get("form_id", "")
                    action = form.get("action", "")
                    method = form.get("method", "")

                    fields = form.get("fields", [])
                    if not fields:
                        # Write row for form with no fields
                        writer.writerow([
                            form_name, form_id, action, method,
                            "No fields detected", "", "", "", "", "", "", "", "", "", ""
                        ])
                    else:
                        for field in fields:
                            # Generate automation selector
                            automation_selector = self._generate_automation_selector(
                                field)

                            # Check if field has data attributes
                            has_data_attrs = "Yes" if field.get(
                                "data_attributes") else "No"

                            # Determine detection method
                            detection_method = field.get(
                                "source", "HTML Parser")

                            writer.writerow([
                                form_name,
                                form_id,
                                action,
                                method,
                                field.get("identifier", ""),
                                field.get("name", ""),
                                field.get("id", ""),
                                field.get("type", ""),
                                field.get("placeholder", ""),
                                field.get("aria_label", ""),
                                field.get("class", ""),
                                "Yes" if field.get(
                                    "required", False) else "No",
                                has_data_attrs,
                                detection_method,
                                automation_selector
                            ])

                # Write summary section
                writer.writerow([])  # Empty row for separation
                writer.writerow(["=== FIELD IDENTIFICATION SUMMARY ==="])
                writer.writerow(["Metric", "Count", "Percentage"])

                # Calculate summary statistics
                total_fields = sum(len(form.get("fields", []))
                                   for form in self.captured_forms)
                named_fields = sum(1 for form in self.captured_forms for field in form.get(
                    "fields", []) if field.get("name"))
                id_fields = sum(1 for form in self.captured_forms for field in form.get(
                    "fields", []) if field.get("id"))
                aria_fields = sum(1 for form in self.captured_forms for field in form.get(
                    "fields", []) if field.get("aria_label"))
                placeholder_fields = sum(1 for form in self.captured_forms for field in form.get(
                    "fields", []) if field.get("placeholder"))
                data_attr_fields = sum(1 for form in self.captured_forms for field in form.get(
                    "fields", []) if field.get("data_attributes"))

                if total_fields > 0:
                    writer.writerow(["Total Fields", total_fields, "100%"])
                    writer.writerow(
                        ["Named Fields", named_fields, f"{round((named_fields/total_fields)*100, 1)}%"])
                    writer.writerow(
                        ["ID Fields", id_fields, f"{round((id_fields/total_fields)*100, 1)}%"])
                    writer.writerow(
                        ["ARIA Labeled", aria_fields, f"{round((aria_fields/total_fields)*100, 1)}%"])
                    writer.writerow(["Placeholder Fields", placeholder_fields,
                                    f"{round((placeholder_fields/total_fields)*100, 1)}%"])
                    writer.writerow(["Data Attribute Fields", data_attr_fields,
                                    f"{round((data_attr_fields/total_fields)*100, 1)}%"])

                    # Calculate comprehensive identification success
                    identifiable = sum(1 for form in self.captured_forms for field in form.get("fields", [])
                                       if (field.get("name") or field.get("id") or field.get("aria_label") or
                                           field.get("placeholder") or field.get("data_attributes")))
                    writer.writerow(["Identifiable Fields", identifiable,
                                    f"{round((identifiable/total_fields)*100, 1)}%"])

                # Write automation recommendations
                writer.writerow([])
                writer.writerow(["=== AUTOMATION RECOMMENDATIONS ==="])
                writer.writerow(
                    ["Field Type", "Recommended Selector", "Reliability"])

                for form in self.captured_forms:
                    for field in form.get("fields", []):
                        selector_quality = self._assess_selector_quality(field)
                        recommended_selector = self._get_best_automation_selector(
                            field)

                        if recommended_selector:
                            writer.writerow([
                                field.get("type", "unknown"),
                                recommended_selector,
                                selector_quality
                            ])

            QMessageBox.information(self, "Export Successful",
                                    f"Enhanced forms data exported to {file_path}\n\n"
                                    f"Includes modern field identification methods:\n"
                                    f"• Name attributes\n"
                                    f"• ID attributes\n"
                                    f"• ARIA labels\n"
                                    f"• Placeholder text\n"
                                    f"• Data attributes\n"
                                    f"• CSS selectors\n"
                                    f"• Automation recommendations")

        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Error exporting enhanced forms: {str(e)}")

    def _assess_selector_quality(self, field):
        """Assess the quality/reliability of field selectors"""
        if field.get("id"):
            return "Excellent (ID-based)"
        elif field.get("name"):
            return "Good (Name-based)"
        elif field.get("aria_label"):
            return "Good (ARIA-based)"
        elif field.get("placeholder"):
            return "Fair (Placeholder-based)"
        elif field.get("data_attributes"):
            return "Fair (Data attribute-based)"
        else:
            return "Poor (No stable identifier)"

    def _get_best_automation_selector(self, field):
        """Get the single best selector for automation purposes"""
        # Return the most reliable selector available
        if field.get("id"):
            return f"#{field['id']}"
        elif field.get("name"):
            return f"[name='{field['name']}']"
        elif field.get("aria_label"):
            return f"[aria-label='{field['aria_label']}']"
        elif field.get("placeholder"):
            return f"[placeholder='{field['placeholder']}']"
        else:
            return "XPath or CSS path needed"

    def _generate_automation_selector(self, field):
        """Generate the best automation selector for a field"""
        selectors = []

        # Priority 1: ID (most reliable)
        if field.get("id"):
            selectors.append(f"#{field['id']}")

        # Priority 2: Name attribute
        if field.get("name"):
            field_type = field.get("type", "")
            if field_type:
                selectors.append(f"{field_type}[name='{field['name']}']")
            else:
                selectors.append(f"[name='{field['name']}']")

        # Priority 3: ARIA label
        if field.get("aria_label"):
            selectors.append(f"[aria-label='{field['aria_label']}']")

        # Priority 4: Placeholder
        if field.get("placeholder"):
            selectors.append(f"[placeholder='{field['placeholder']}']")

        # Priority 5: Data attributes
        data_attrs = field.get("data_attributes", {})
        if data_attrs:
            for attr_name, attr_value in list(data_attrs.items())[:1]:
                selectors.append(f"[{attr_name}='{attr_value}']")

        return selectors[0] if selectors else "No reliable selector available"

    def _get_best_form_identifier(self, form, form_index):
        """Get the best identifier for a form using multiple attributes"""
        # Try different identification methods in priority order
        identifiers = []

        # 1. Form name
        if form.get("form_name") or form.get("name"):
            identifiers.append(form.get("form_name") or form.get("name"))

        # 2. Form ID
        if form.get("form_id") or form.get("id"):
            identifiers.append(f"#{form.get('form_id') or form.get('id')}")

        # 3. Action-based identification
        action = form.get("action", "")
        if action and action != "":
            # Extract meaningful part from action URL
            if "/" in action:
                action_part = action.split("/")[-1]
                if action_part and action_part != "":
                    identifiers.append(f"→{action_part}")

        # 4. CSS class-based identification
        form_class = form.get("form_class") or form.get("class", "")
        if form_class:
            class_parts = form_class.split()
            if class_parts:
                identifiers.append(f".{class_parts[0]}")

        # Return the best identifier or fallback
        if identifiers:
            return " | ".join(identifiers[:2])  # Show top 2 identifiers
        else:
            return f"Form {form_index}"

    def _get_best_field_identifier(self, field, field_index=None):
        """Get the best identifier for a field using multiple modern attributes"""
        # Try different identification methods in priority order
        identifiers = []

        # 1. Field name (traditional)
        if field.get("name"):
            identifiers.append(field.get("name"))

        # 2. Field ID (modern)
        if field.get("field_id") or field.get("id"):
            field_id = field.get("field_id") or field.get("id")
            identifiers.append(f"#{field_id}")

        # 3. ARIA label (accessibility)
        if field.get("aria_label"):
            aria_label = field.get("aria_label")
            if len(aria_label) > 20:
                aria_label = aria_label[:20] + "..."
            identifiers.append(f"[aria:{aria_label}]")

        # 4. Placeholder text (UX)
        if field.get("placeholder"):
            placeholder = field.get("placeholder")
            if len(placeholder) > 20:
                placeholder = placeholder[:20] + "..."
            identifiers.append(f"'{placeholder}'")

        # 5. Button text content
        if field.get("text") and field.get("type", "").startswith("button"):
            button_text = field.get("text")
            if len(button_text) > 20:
                button_text = button_text[:20] + "..."
            identifiers.append(f'"{button_text}"')

        # 6. Data attributes (modern)
        data_attrs = field.get("data_attributes", {})
        if data_attrs:
            # Show first data attribute
            for attr_name, attr_value in list(data_attrs.items())[:1]:
                if attr_value:
                    attr_display = str(attr_value)[:15]
                    if len(str(attr_value)) > 15:
                        attr_display += "..."
                    identifiers.append(f"[{attr_name}:{attr_display}]")

        # 7. CSS class-based identification
        field_class = field.get("class", "")
        if field_class and not any(id in identifiers for id in identifiers):
            class_parts = field_class.split()
            if class_parts:
                identifiers.append(f".{class_parts[0]}")

        # Return the best identifier or fallback
        if identifiers:
            return " | ".join(identifiers[:2])  # Show top 2 identifiers
        else:
            field_type = field.get("type", "unknown")
            return f"field_{field_index or 'unknown'} ({field_type})"

    def _add_comprehensive_field_properties(self, field_item, field):
        """Add comprehensive field properties with modern attributes"""
        # Basic properties
        field_type = field.get("type", "unknown")
        self.addFormProperty(field_item, "🔧 Type", field_type)

        # Identification attributes
        if field.get("name"):
            self.addFormProperty(field_item, "🏷️ Name", field.get("name"))

        if field.get("field_id") or field.get("id"):
            self.addFormProperty(field_item, "🆔 ID", field.get(
                "field_id") or field.get("id"))

        # Modern attributes
        if field.get("aria_label"):
            self.addFormProperty(field_item, "♿ ARIA Label",
                                 field.get("aria_label"))

        if field.get("placeholder"):
            self.addFormProperty(field_item, "💬 Placeholder",
                                 field.get("placeholder"))

        # Form control attributes
        if field.get("required"):
            self.addFormProperty(field_item, "⚠️ Required", "Yes")

        if field.get("disabled"):
            self.addFormProperty(field_item, "🚫 Disabled", "Yes")

        # Content attributes
        if field.get("value"):
            value_display = field.get("value")
            if len(value_display) > 50:
                value_display = value_display[:50] + "..."
            self.addFormProperty(field_item, "📝 Value", value_display)

        if field.get("text") and field_type.startswith("button"):
            self.addFormProperty(
                field_item, "📄 Button Text", field.get("text"))

        # Styling attributes
        if field.get("class"):
            class_display = field.get("class")
            if len(class_display) > 50:
                class_display = class_display[:50] + "..."
            self.addFormProperty(field_item, "🎨 CSS Classes", class_display)

        # Behavior attributes
        if field.get("autocomplete"):
            self.addFormProperty(
                field_item, "🔄 Autocomplete", field.get("autocomplete"))

        if field.get("onclick"):
            onclick_display = field.get("onclick")[:50]
            if len(field.get("onclick", "")) > 50:
                onclick_display += "..."
            self.addFormProperty(field_item, "🖱️ OnClick", onclick_display)

        # Data attributes section
        data_attrs = field.get("data_attributes", {})
        if data_attrs and isinstance(data_attrs, dict):
            data_item = QTreeWidgetItem(field_item)
            data_item.setText(0, "📊 Data Attributes")
            data_item.setText(1, f"{len(data_attrs)} attributes")

            # Show first 5
            for attr_name, attr_value in list(data_attrs.items())[:5]:
                attr_item = QTreeWidgetItem(data_item)
                attr_item.setText(0, attr_name)

                # Format attribute value
                attr_display = str(attr_value)
                if len(attr_display) > 100:
                    attr_display = attr_display[:100] + "..."
                attr_item.setText(1, attr_display)

        # CSS selectors section
        css_selectors = field.get("css_selectors", [])
        if css_selectors and isinstance(css_selectors, list):
            css_item = QTreeWidgetItem(field_item)
            css_item.setText(0, "🎯 CSS Selectors")
            css_item.setText(1, f"{len(css_selectors)} selectors")

            # Show first 3 selectors
            for i, selector in enumerate(css_selectors[:3]):
                selector_item = QTreeWidgetItem(css_item)
                selector_item.setText(0, f"Selector {i+1}")
                selector_item.setText(1, str(selector))

        # Detection source information
        if field.get("source"):
            detection_source = field.get("source", "")
            if detection_source == "selenium":
                self.addFormProperty(
                    field_item, "🔍 Detection", "🤖 Selenium WebDriver")
            elif detection_source == "shadow_dom":
                self.addFormProperty(field_item, "🔍 Detection", "🌑 Shadow DOM")
            else:
                self.addFormProperty(
                    field_item, "🔍 Detection", "📄 HTML Parser")

        # Select options processing
        if field.get("type") == "select" and field.get("options"):
            options = field.get("options", [])
            options_item = QTreeWidgetItem(field_item)
            options_item.setText(0, "📋 Select Options")
            options_item.setText(1, f"{len(options)} options")

            for j, option in enumerate(options[:10]):  # Show first 10 options
                option_item = QTreeWidgetItem(options_item)
                if isinstance(option, dict):
                    option_text = option.get(
                        "text", "") or option.get("value", "")
                    selected = " (Selected)" if option.get(
                        "selected", False) else ""
                    option_item.setText(0, f"Option {j+1}")
                    option_item.setText(1, f"{option_text}{selected}")
                else:
                    option_item.setText(0, f"Option {j+1}")
                    option_item.setText(1, str(option))

    def debug_form_data(self, form, form_index):
        """Debug helper to understand form data structure"""
        print(f"\n🐛 DEBUG Form {form_index}:")
        print(f"   📋 Form keys: {list(form.keys())}")

        for key, value in form.items():
            if isinstance(value, (str, int, bool)):
                print(f"   {key}: {value}")
            elif isinstance(value, list):
                print(f"   {key}: [list with {len(value)} items]")
                if value and len(value) > 0:
                    print(f"      First item: {value[0]}")
            elif isinstance(value, dict):
                print(f"   {key}: [dict with keys: {list(value.keys())}]")
            else:
                print(f"   {key}: {type(value).__name__}")

        # Check specifically for field-related data
        field_indicators = ["HAS_FIELD", "fields",
                            "field_count", "field_details"]
        print(f"   🔍 Field indicators found:")
        for indicator in field_indicators:
            if indicator in form:
                print(f"      ✅ {indicator}: {type(form[indicator]).__name__}")
            else:
                print(f"      ❌ {indicator}: Not found")
# For testing the export functionality
