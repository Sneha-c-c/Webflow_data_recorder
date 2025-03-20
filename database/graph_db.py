from neo4j import GraphDatabase
import networkx as nx
import time

# Graph Database (Neo4j) Connection
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Welcome123$"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# NetworkX graph for in-memory representation
G = nx.DiGraph()

# Initialize database with required constraints and indexes
def init_database():
    with driver.session() as session:
        try:
            # Check Neo4j version first to use appropriate syntax
            version_result = session.run("CALL dbms.components() YIELD versions RETURN versions[0] as version")
            version_record = version_result.single()
            version = version_record["version"] if version_record else "unknown"
            
            print(f"Neo4j version: {version}")
            
            # Neo4j 5.x+ syntax
            if version.startswith("5"):
                # Create constraints using Neo4j 5.x syntax
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Page) REQUIRE p.url IS UNIQUE")
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:Form) REQUIRE f.id IS UNIQUE")
                
                # Create indexes for better performance
                session.run("CREATE INDEX IF NOT EXISTS FOR (p:Page) ON (p.title)")
                session.run("CREATE INDEX IF NOT EXISTS FOR (p:Page) ON (p.timestamp)")
                session.run("CREATE INDEX IF NOT EXISTS FOR (p:Page) ON (p.session_id)")
            # Neo4j 4.x syntax
            elif version.startswith("4"):
                # Create constraints using Neo4j 4.x syntax
                session.run("CREATE CONSTRAINT IF NOT EXISTS ON (p:Page) ASSERT p.url IS UNIQUE")
                session.run("CREATE CONSTRAINT IF NOT EXISTS ON (f:Form) ASSERT f.id IS UNIQUE")
                
                # Create indexes for better performance
                session.run("CREATE INDEX IF NOT EXISTS FOR (p:Page) ON (p.title)")
                session.run("CREATE INDEX IF NOT EXISTS FOR (p:Page) ON (p.timestamp)")
                session.run("CREATE INDEX IF NOT EXISTS FOR (p:Page) ON (p.session_id)")
            # Neo4j 3.x syntax (older)
            else:
                # Create constraints using Neo4j 3.x syntax (no IF NOT EXISTS)
                try:
                    session.run("CREATE CONSTRAINT ON (p:Page) ASSERT p.url IS UNIQUE")
                except Exception:
                    # Constraint might already exist
                    pass
                    
                try:
                    session.run("CREATE CONSTRAINT ON (f:Form) ASSERT f.id IS UNIQUE")
                except Exception:
                    # Constraint might already exist
                    pass
                    
                # Create indexes (older syntax)
                try:
                    session.run("CREATE INDEX ON :Page(title)")
                    session.run("CREATE INDEX ON :Page(timestamp)")
                    session.run("CREATE INDEX ON :Page(session_id)")
                except Exception:
                    # Indexes might already exist
                    pass
            
            return True
        except Exception as e:
            print(f"Error detecting Neo4j version or creating constraints: {e}")
            
            # Fallback: try minimal setup without constraints
            try:
                # Just create basic indices without constraints
                session.run("CREATE INDEX index_page_url IF NOT EXISTS FOR (p:Page) ON (p.url)")
                print("Fallback: Created basic index only")
                return True
            except Exception as e2:
                print(f"Fallback failed too: {e2}")
                return False

# Store in Neo4j
def store_in_neo4j(url, metadata, referrer=None, session_id=None):
    with driver.session() as session:
        try:
            # Determine if this is a special page type
            is_alert = metadata.get("is_alert", False)
            page_type = "Alert" if is_alert else "Page"
            
            # Get current session ID from history manager if not provided
            if not session_id:
                from database.history_manager import history_manager
                if history_manager.current_session:
                    session_id = history_manager.current_session.id
            
            # Create page node with detailed metadata
            session.run(f"""
            MERGE (p:{page_type} {{url: $url}})
            SET p.title = $title,
                p.summary = $summary,
                p.timestamp = $timestamp,
                p.is_alert = $is_alert,
                p.session_id = $session_id
            """, 
                url=url, 
                title=metadata.get("title", ""), 
                summary=metadata.get("summary", ""),
                timestamp=metadata.get("timestamp", int(time.time() * 1000)),
                is_alert=is_alert,
                session_id=session_id
            )
            
            # Store headings
            headings = metadata.get("headings", [])
            if headings:
                session.run("""
                MATCH (p {url: $url})
                SET p.headings = $headings
                """, url=url, headings=str(headings))
            
            # Store standalone fields
            fields = metadata.get("fields", [])
            if fields:
                session.run("""
                MATCH (p {url: $url})
                SET p.standalone_fields = $fields
                """, url=url, fields=str(fields))
            
            # Store actions
            actions = metadata.get("actions", [])
            if actions:
                session.run("""
                MATCH (p {url: $url})
                SET p.actions = $actions
                """, url=url, actions=str(actions))
            
            # Store scripts
            scripts = metadata.get("scripts", [])
            if scripts:
                session.run("""
                MATCH (p {url: $url})
                SET p.scripts = $scripts
                """, url=url, scripts=str(scripts))
            
            # Store meta tags as separate properties
            for key, value in metadata.get("meta_tags", {}).items():
                # Replace dots and special characters in property names
                safe_key = key.replace(".", "_").replace(":", "_").replace("-", "_")
                session.run("""
                MATCH (p {url: $url})
                SET p.meta_$key = $value
                """, url=url, key=safe_key, value=value)
            
            # Create relationship from referrer if available
            if referrer:
                session.run("""
                MATCH (r {url: $referrer})
                MATCH (p {url: $url})
                MERGE (r)-[:LEADS_TO]->(p)
                """, referrer=referrer, url=url)
                
                # Also update the in-memory graph
                G.add_edge(referrer, url)
            else:
                # Ensure the node exists in the in-memory graph
                G.add_node(url)
                
            # Store forms as separate nodes connected to the page
            form_index = 0
            for form in metadata.get("forms", []):
                form_id = f"{url}_form_{form_index}"
                
                # Create the Form node with basic properties
                session.run("""
                MATCH (p {url: $url})
                MERGE (f:Form {id: $form_id})
                SET f.action = $action,
                    f.method = $method,
                    f.form_name = $form_name,
                    f.form_id = $form_id_attr,
                    f.form_class = $form_class,
                    f.enctype = $enctype,
                    f.target = $target,
                    f.field_count = $field_count,
                    f.session_id = $session_id
                MERGE (p)-[:HAS_FORM]->(f)
                """, 
                    url=url, 
                    form_id=form_id, 
                    action=form.get("action", ""), 
                    method=form.get("method", ""),
                    form_name=form.get("name", ""),
                    form_id_attr=form.get("id", ""),
                    form_class=str(form.get("class", [])),
                    enctype=form.get("enctype", ""),
                    target=form.get("target", ""),
                    field_count=len(form.get("fields", [])),
                    session_id=session_id
                )
                
                # Store each field as a separate node
                field_index = 0
                for field in form.get("fields", []):
                    field_id = f"{form_id}_field_{field_index}"
                    field_type = field.get("type", "text")
                    
                    # Create the Field node
                    session.run("""
                    MATCH (f:Form {id: $form_id})
                    MERGE (field:FormField {id: $field_id})
                    SET field.name = $name,
                        field.type = $type,
                        field.field_id = $field_id_attr,
                        field.placeholder = $placeholder,
                        field.value = $value,
                        field.required = $required,
                        field.field_index = $field_index,
                        field.session_id = $session_id
                    MERGE (f)-[:HAS_FIELD]->(field)
                    """,
                        form_id=form_id,
                        field_id=field_id,
                        name=field.get("name", ""),
                        type=field_type,
                        field_id_attr=field.get("id", ""),
                        placeholder=field.get("placeholder", ""),
                        value=field.get("value", ""),
                        required=field.get("required", False),
                        field_index=field_index,
                        session_id=session_id
                    )
                    
                    # For select fields, store options
                    if field_type == "select" and "options" in field:
                        options = field.get("options", [])
                        for option_index, option in enumerate(options):
                            option_id = f"{field_id}_option_{option_index}"
                            session.run("""
                            MATCH (field:FormField {id: $field_id})
                            MERGE (option:SelectOption {id: $option_id})
                            SET option.value = $value,
                                option.text = $text,
                                option.selected = $selected,
                                option.option_index = $option_index,
                                option.session_id = $session_id
                            MERGE (field)-[:HAS_OPTION]->(option)
                            """,
                                field_id=field_id,
                                option_id=option_id,
                                value=option.get("value", ""),
                                text=option.get("text", ""),
                                selected=option.get("selected", False),
                                option_index=option_index,
                                session_id=session_id
                            )
                    
                    field_index += 1
                
                form_index += 1
                
            return True
        except Exception as e:
            print(f"Error storing in Neo4j: {e}")
            return False

# Query flow data from Neo4j with optional session filter
# Query flow data from Neo4j with optional session filter
def get_flow_data(session_id=None):
    """Retrieve flow data from Neo4j for visualization"""
    with driver.session() as session:
        try:
            # Get all paths in the graph
            if session_id:
                # Improved filtering by session - ensure both nodes in the path belong to the same session
                result = session.run("""
                MATCH path = (a)-[:LEADS_TO*]->(b)
                WHERE NOT a:Form AND NOT b:Form
                AND a.session_id = $session_id AND b.session_id = $session_id
                RETURN path
                """, session_id=session_id)
            else:
                # Get all paths
                result = session.run("""
                MATCH path = (a)-[:LEADS_TO*]->(b)
                WHERE NOT a:Form AND NOT b:Form
                RETURN path
                """)
            
            # Process the results
            flows = []
            for record in result:
                path = record["path"]
                flow_path = []
                
                for rel in path.relationships:
                    start_node = rel.start_node
                    end_node = rel.end_node
                    
                    # Get properties
                    start_url = start_node["url"]
                    start_title = start_node.get("title", "Unknown")
                    
                    end_url = end_node["url"]
                    end_title = end_node.get("title", "Unknown")
                    
                    # Determine if this is a special node type
                    is_alert = end_node.get("is_alert", False)
                    
                    # Add to path
                    flow_path.append({
                        "from_url": start_url, 
                        "from_title": start_title,
                        "to_url": end_url,
                        "to_title": end_title,
                        "is_alert": is_alert
                    })
                
                flows.append(flow_path)
            
            return flows
        except Exception as e:
            print(f"Error getting flow data: {e}")
            return []

# Query page details from Neo4j
def get_page_details(url):
    """Get detailed information about a specific page from Neo4j"""
    with driver.session() as session:
        try:
            result = session.run("""
            MATCH (p {url: $url})
            OPTIONAL MATCH (p)-[:HAS_FORM]->(f:Form)
            RETURN p, collect(f) as forms
            """, url=url)
            
            record = result.single()
            if not record:
                return None
                
            page = record["p"]
            forms = record["forms"]
            
            # Get all properties
            properties = dict(page.items())
            
            # Process forms
            form_details = []
            for form in forms:
                if form:  # Some forms might be null
                    form_details.append(dict(form.items()))
            
            properties["forms"] = form_details
            
            # Convert timestamp to readable format if available
            if "timestamp" in properties:
                try:
                    timestamp = properties["timestamp"]
                    if isinstance(timestamp, int):
                        from datetime import datetime
                        # Convert milliseconds to seconds
                        dt = datetime.fromtimestamp(timestamp / 1000)
                        properties["timestamp_readable"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
                
            return properties
        except Exception as e:
            print(f"Error getting page details: {e}")
            return None

# Get statistics about captured data
def get_capture_stats(session_id=None):
    """Get statistics about the captured data"""
    with driver.session() as session:
        try:
            # Get counts of different node types
            if session_id:
                # Filter by session
                result = session.run("""
                MATCH (p:Page)
                WHERE p.session_id = $session_id
                WITH count(p) as page_count
                MATCH (f:Form)
                WHERE f.session_id = $session_id
                WITH page_count, count(f) as form_count
                MATCH (a:Alert)
                WHERE a.session_id = $session_id
                WITH page_count, form_count, count(a) as alert_count
                MATCH ()-[r:LEADS_TO]->()
                RETURN page_count, form_count, alert_count, count(r) as flow_count
                """, session_id=session_id)
            else:
                # Get all stats
                result = session.run("""
                MATCH (p:Page)
                WITH count(p) as page_count
                OPTIONAL MATCH (f:Form)
                WITH page_count, count(f) as form_count
                OPTIONAL MATCH (a:Alert)
                WITH page_count, form_count, count(a) as alert_count
                OPTIONAL MATCH ()-[r:LEADS_TO]->()
                RETURN page_count, form_count, alert_count, count(r) as flow_count
                """)
            
            record = result.single()
            if not record:
                return {
                    "pages": 0,
                    "forms": 0,
                    "alerts": 0,
                    "flows": 0
                }
                
            return {
                "pages": record["page_count"],
                "forms": record["form_count"],
                "alerts": record["alert_count"],
                "flows": record["flow_count"]
            }
        except Exception as e:
            print(f"Error getting capture stats: {e}")
            return {
                "pages": 0,
                "forms": 0,
                "alerts": 0,
                "flows": 0,
                "error": str(e)
            }

# Close the Neo4j connection when the application exits
def close_neo4j_connection():
    if driver:
        driver.close()

# Initialize the database when this module is imported
init_database()