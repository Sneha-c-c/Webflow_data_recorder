import time
import psycopg2
import numpy as np
from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup
from datetime import datetime

# Initialize embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Vector Database (PostgreSQL with pgvector) Connection
DB_CONFIG = {
    "dbname": "vector_db",
    "user": "harid",
    "password": "",
    "host": "localhost"
}

# Global connection and cursor
PG_CONN = None
PG_CURSOR = None

def connect_to_db():
    """Create a connection to the PostgreSQL database"""
    global PG_CONN, PG_CURSOR
    
    try:
        PG_CONN = psycopg2.connect(**DB_CONFIG)
        PG_CURSOR = PG_CONN.cursor()
        return True
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return False

def init_database():
    """Initialize the database with required tables and extensions"""
    global PG_CONN, PG_CURSOR
    
    if not PG_CONN or not PG_CURSOR:
        if not connect_to_db():
            return False
    
    try:
        # Check if pgvector extension exists
        PG_CURSOR.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        has_vector = PG_CURSOR.fetchone()[0]
        
        if not has_vector:
            # Create pgvector extension
            PG_CURSOR.execute("CREATE EXTENSION IF NOT EXISTS vector")
        
        # Create improved table with additional columns
        PG_CURSOR.execute("""
        CREATE TABLE IF NOT EXISTS page_embeddings (
            url TEXT PRIMARY KEY, 
            embedding vector(384), 
            content TEXT, 
            content_type TEXT DEFAULT 'html',
            timestamp FLOAT,
            title TEXT,
            is_alert BOOLEAN DEFAULT false,
            session_id TEXT
        );
        """)
        
        # Create index for faster similarity search
        PG_CURSOR.execute("""
        CREATE INDEX IF NOT EXISTS page_embeddings_embedding_idx 
        ON page_embeddings USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
        """)
        
        # Create index for session_id for faster filtering
        PG_CURSOR.execute("""
        CREATE INDEX IF NOT EXISTS page_embeddings_session_idx 
        ON page_embeddings (session_id);
        """)
        
        PG_CONN.commit()
        return True
    except Exception as e:
        print(f"Error setting up vector DB: {e}")
        PG_CONN.rollback()
        return False

# Store in Vector DB
def store_in_pgvector(url, content, metadata=None, session_id=None):
    """Store page content and embeddings in the vector database"""
    global PG_CONN, PG_CURSOR
    
    if not PG_CONN or not PG_CURSOR:
        if not connect_to_db():
            return False
    
    try:
        # Extract text content
        if content and isinstance(content, str):
            if metadata and metadata.get("is_alert", False):
                # For alerts, use the content directly (it's already simple text)
                text_content = content
                content_type = "alert"
            else:
                # For regular HTML pages, extract text
                soup = BeautifulSoup(content, "html.parser")
                text_content = soup.get_text().strip()
                content_type = "html"
        else:
            text_content = "No content available"
            content_type = "unknown"
        
        # Create embedding
        embedding = model.encode(text_content).astype('float32')
        
        # Get title from metadata
        title = metadata.get("title", "") if metadata else ""
        is_alert = metadata.get("is_alert", False) if metadata else False
        
        # Get current session ID if not provided
        if not session_id:
            from database.history_manager import history_manager
            if history_manager.current_session:
                session_id = history_manager.current_session.id
        
        # Store URL, embedding and text content for retrieval
        PG_CURSOR.execute("""
            INSERT INTO page_embeddings 
            (url, embedding, content, content_type, timestamp, title, is_alert, session_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) 
            ON CONFLICT (url) DO UPDATE 
            SET embedding = %s, 
                content = %s, 
                content_type = %s,
                timestamp = %s,
                title = %s,
                is_alert = %s,
                session_id = %s;
        """, (
            url, embedding.tolist(), text_content, content_type, time.time(), title, is_alert, session_id,
            embedding.tolist(), text_content, content_type, time.time(), title, is_alert, session_id
        ))
        
        PG_CONN.commit()
        return True
    except Exception as e:
        print(f"Error storing in vector DB: {e}")
        PG_CONN.rollback()
        return False

# Query page content from Vector DB
def get_page_content(url):
    """Get the stored text content for a page from Vector DB"""
    global PG_CONN, PG_CURSOR
    
    if not PG_CONN or not PG_CURSOR:
        if not connect_to_db():
            return None
    
    try:
        PG_CURSOR.execute("""
        SELECT content, timestamp, content_type, title, is_alert, session_id 
        FROM page_embeddings
        WHERE url = %s
        """, (url,))
        
        result = PG_CURSOR.fetchone()
        if result:
            content, timestamp, content_type, title, is_alert, session_id = result
            
            # Format datetime
            readable_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"
            
            return {
                "content": content,
                "timestamp": timestamp,
                "datetime": readable_time,
                "content_type": content_type,
                "title": title,
                "is_alert": is_alert,
                "session_id": session_id
            }
        return None
    except Exception as e:
        print(f"Error retrieving page content: {e}")
        return None

# Find similar pages
def find_similar_pages(url, limit=5, session_id=None):
    """Find pages with similar content based on vector embeddings"""
    global PG_CONN, PG_CURSOR
    
    if not PG_CONN or not PG_CURSOR:
        if not connect_to_db():
            return []
    
    try:
        # First get the embedding for the target URL
        PG_CURSOR.execute("""
        SELECT embedding FROM page_embeddings
        WHERE url = %s
        """, (url,))
        
        result = PG_CURSOR.fetchone()
        if not result:
            return []
            
        target_embedding = result[0]
        
        # Find similar pages using cosine similarity
        if session_id:
            # Filter by session
            PG_CURSOR.execute("""
            SELECT url, title, 1 - (embedding <=> %s) as similarity
            FROM page_embeddings
            WHERE url != %s AND session_id = %s
            ORDER BY similarity DESC
            LIMIT %s
            """, (target_embedding, url, session_id, limit))
        else:
            # All sessions
            PG_CURSOR.execute("""
            SELECT url, title, 1 - (embedding <=> %s) as similarity
            FROM page_embeddings
            WHERE url != %s
            ORDER BY similarity DESC
            LIMIT %s
            """, (target_embedding, url, limit))
        
        similar_pages = []
        for similar_url, title, similarity in PG_CURSOR.fetchall():
            similar_pages.append({
                "url": similar_url,
                "title": title or similar_url,
                "similarity": round(similarity * 100, 2)  # Convert to percentage
            })
            
        return similar_pages
    except Exception as e:
        print(f"Error finding similar pages: {e}")
        return []

# Search pages by keyword
def search_pages(query, limit=10, session_id=None):
    """Search pages by keyword in content"""
    global PG_CONN, PG_CURSOR
    
    if not PG_CONN or not PG_CURSOR:
        if not connect_to_db():
            return []
    
    try:
        # Create embedding for the query
        query_embedding = model.encode(query).astype('float32')
        
        # Search using vector similarity
        if session_id:
            # Filter by session
            PG_CURSOR.execute("""
            SELECT url, title, 1 - (embedding <=> %s) as similarity
            FROM page_embeddings
            WHERE session_id = %s
            ORDER BY similarity DESC
            LIMIT %s
            """, (query_embedding.tolist(), session_id, limit))
        else:
            # All sessions
            PG_CURSOR.execute("""
            SELECT url, title, 1 - (embedding <=> %s) as similarity
            FROM page_embeddings
            ORDER BY similarity DESC
            LIMIT %s
            """, (query_embedding.tolist(), limit))
        
        results = []
        for url, title, similarity in PG_CURSOR.fetchall():
            # Only include results with reasonable similarity
            if similarity > 0.5:  # Adjust threshold as needed
                results.append({
                    "url": url,
                    "title": title or url,
                    "similarity": round(similarity * 100, 2)
                })
        
        return results
    except Exception as e:
        print(f"Error searching pages: {e}")
        return []

# Get all pages in the database
def get_all_pages(limit=100, offset=0, session_id=None):
    """Get all pages in the database, with pagination"""
    global PG_CONN, PG_CURSOR
    
    if not PG_CONN or not PG_CURSOR:
        if not connect_to_db():
            return []
    
    try:
        if session_id:
            # Filter by session
            PG_CURSOR.execute("""
            SELECT url, title, content_type, timestamp, is_alert, session_id
            FROM page_embeddings
            WHERE session_id = %s
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """, (session_id, limit, offset))
        else:
            # All sessions
            PG_CURSOR.execute("""
            SELECT url, title, content_type, timestamp, is_alert, session_id
            FROM page_embeddings
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """, (limit, offset))
        
        pages = []
        for url, title, content_type, timestamp, is_alert, session_id in PG_CURSOR.fetchall():
            # Format datetime
            readable_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"
            
            pages.append({
                "url": url,
                "title": title or url,
                "content_type": content_type,
                "timestamp": timestamp,
                "datetime": readable_time,
                "is_alert": is_alert,
                "session_id": session_id
            })
        
        return pages
    except Exception as e:
        print(f"Error getting all pages: {e}")
        return []

# Get database statistics
def get_db_stats(session_id=None):
    """Get statistics about the vector database"""
    global PG_CONN, PG_CURSOR
    
    if not PG_CONN or not PG_CURSOR:
        if not connect_to_db():
            return {}
    
    try:
        # Get total count
        if session_id:
            PG_CURSOR.execute("SELECT COUNT(*) FROM page_embeddings WHERE session_id = %s", (session_id,))
        else:
            PG_CURSOR.execute("SELECT COUNT(*) FROM page_embeddings")
            
        total_count = PG_CURSOR.fetchone()[0]
        
        # Get counts by content type
        if session_id:
            PG_CURSOR.execute("""
            SELECT content_type, COUNT(*) 
            FROM page_embeddings 
            WHERE session_id = %s
            GROUP BY content_type
            """, (session_id,))
        else:
            PG_CURSOR.execute("""
            SELECT content_type, COUNT(*) 
            FROM page_embeddings 
            GROUP BY content_type
            """)
            
        content_types = {row[0]: row[1] for row in PG_CURSOR.fetchall()}
        
        # Get alert count
        if session_id:
            PG_CURSOR.execute("""
            SELECT COUNT(*) FROM page_embeddings 
            WHERE is_alert = true AND session_id = %s
            """, (session_id,))
        else:
            PG_CURSOR.execute("SELECT COUNT(*) FROM page_embeddings WHERE is_alert = true")
            
        alert_count = PG_CURSOR.fetchone()[0]
        
        # Get earliest and latest timestamps
        if session_id:
            PG_CURSOR.execute("""
            SELECT MIN(timestamp), MAX(timestamp) 
            FROM page_embeddings
            WHERE session_id = %s
            """, (session_id,))
        else:
            PG_CURSOR.execute("SELECT MIN(timestamp), MAX(timestamp) FROM page_embeddings")
            
        min_ts, max_ts = PG_CURSOR.fetchone()
        
        return {
            "total": total_count,
            "content_types": content_types,
            "alerts": alert_count,
            "first_capture": datetime.fromtimestamp(min_ts).strftime("%Y-%m-%d %H:%M:%S") if min_ts else None,
            "latest_capture": datetime.fromtimestamp(max_ts).strftime("%Y-%m-%d %H:%M:%S") if max_ts else None
        }
    except Exception as e:
        print(f"Error getting DB stats: {e}")
        return {
            "error": str(e)
        }

# Close the PostgreSQL connection when the application exits
def close_pg_connection():
    global PG_CONN, PG_CURSOR
    if PG_CURSOR:
        PG_CURSOR.close()
    if PG_CONN:
        PG_CONN.close()

# Initialize connection and database when this module is imported
connect_to_db()
init_database()