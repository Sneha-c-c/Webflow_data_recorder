import os
import json
import time
from datetime import datetime
from database.graph_db import driver
from database.vector_db import PG_CONN, PG_CURSOR

class CaptureSession:
    def __init__(self, id=None, website=None, start_time=None, end_time=None, page_count=0, description=""):
        self.id = id or f"session_{int(time.time())}"
        self.website = website
        self.start_time = start_time or time.time()
        self.end_time = end_time
        self.page_count = page_count
        self.description = description
    
    def to_dict(self):
        return {
            "id": self.id,
            "website": self.website,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "page_count": self.page_count,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id"),
            website=data.get("website"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            page_count=data.get("page_count", 0),
            description=data.get("description", "")
        )
    
    @property
    def formatted_start_time(self):
        return datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S")
    
    @property
    def formatted_end_time(self):
        if self.end_time:
            return datetime.fromtimestamp(self.end_time).strftime("%Y-%m-%d %H:%M:%S")
        return "Active"
    
    @property
    def duration(self):
        if self.end_time:
            duration_sec = self.end_time - self.start_time
            minutes, seconds = divmod(int(duration_sec), 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        return "Active"

    @property
    def date(self):
        """Return date as a datetime.date object for filtering"""
        return datetime.fromtimestamp(self.start_time).date()

class HistoryManager:
    def __init__(self, history_file="./capture_history.json"):
        self.history_file = history_file
        self.current_session = None
        self.sessions = []
        self.load_history()
        
        # Create sample data if no sessions exist
        if not self.sessions:
            self.create_sample_data()
    
    def load_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                self.sessions = [CaptureSession.from_dict(session) for session in data]
                print(f"Loaded {len(self.sessions)} sessions from history file")
            else:
                print(f"History file not found at: {self.history_file}")
        except Exception as e:
            print(f"Error loading history: {e}")
            self.sessions = []
    
    def save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump([session.to_dict() for session in self.sessions], f, indent=2)
            print(f"Saved {len(self.sessions)} sessions to history file")
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def create_sample_data(self):
        """Create sample session data if none exists"""
        print("Creating sample session data...")
        
        # Sample websites
        websites = [
            "example.com",
            "shopping.example.com",
            "news.example.org",
            "blog.example.net",
            "dashboard.example.io"
        ]
        
        # Create sessions over the past month
        now = time.time()
        for i in range(10):
            # Create session with random data
            days_ago = i * 3  # Spread sessions across the month
            start_time = now - (days_ago * 86400)  # 86400 seconds in a day
            end_time = start_time + (3600 * (i % 3 + 1))  # 1-3 hours duration
            
            website = websites[i % len(websites)]
            
            # Create session
            session = CaptureSession(
                id=f"sample_session_{i+1}",
                website=website,
                start_time=start_time,
                end_time=end_time,
                page_count=(i+1) * 5,  # 5-50 pages
                description=f"Sample session for {website}" if i % 2 == 0 else ""
            )
            
            self.sessions.append(session)
        
        # Save the sample data
        self.save_history()
        print(f"Created {len(self.sessions)} sample sessions")
    
    def start_session(self, website):
        # End any active session first
        self.end_current_session()
        
        # Create new session
        self.current_session = CaptureSession(website=website)
        self.sessions.append(self.current_session)
        self.save_history()
        
        print(f"Started new session: {self.current_session.id} for {website}")
        return self.current_session

    def end_current_session(self):
        if self.current_session and not self.current_session.end_time:
            # Update page count
            self.current_session.page_count = self.get_page_count(self.current_session.id)
            self.current_session.end_time = time.time()
            self.save_history()
            
            print(f"Ended session: {self.current_session.id} with {self.current_session.page_count} pages")
            self.current_session = None
            return True
        return False
    
    def get_page_count(self, session_id):
        """Get page count from Neo4j for current session"""
        count = 0
        try:
            with driver.session() as session:
                # Count pages captured during this session
                result = session.run("""
                MATCH (p) 
                WHERE p.session_id = $session_id
                RETURN count(p) as page_count
                """, session_id=session_id)
                record = result.single()
                if record:
                    count = record["page_count"]
        except Exception as e:
            print(f"Error getting page count: {e}")
        return count
    
    def update_session(self, session_id, description=None):
        """Update session details"""
        for session in self.sessions:
            if session.id == session_id:
                if description is not None:
                    session.description = description
                # Update page count
                session.page_count = self.get_page_count(session_id)
                self.save_history()
                print(f"Updated session: {session_id}")
                return True
        print(f"Session not found: {session_id}")
        return False
    
    def delete_session(self, session_id):
        """Delete a session and its associated data"""
        # First remove from Neo4j
        try:
            with driver.session() as session:
                # Delete all nodes and relationships for this session
                session.run("""
                MATCH (n)
                WHERE n.session_id = $session_id
                DETACH DELETE n
                """, session_id=session_id)
        except Exception as e:
            print(f"Error deleting session from Neo4j: {e}")
        
        # Then remove from vector DB
        try:
            PG_CURSOR.execute("""
            DELETE FROM page_embeddings
            WHERE session_id = %s
            """, (session_id,))
            PG_CONN.commit()
        except Exception as e:
            print(f"Error deleting session from vector DB: {e}")
            PG_CONN.rollback()
        
        # Remove from history
        self.sessions = [s for s in self.sessions if s.id != session_id]
        self.save_history()
        
        print(f"Deleted session: {session_id}")
        return True
    
    def get_session_by_id(self, session_id):
        """Get session by ID"""
        for session in self.sessions:
            if session.id == session_id:
                return session
        return None
    
    def get_sessions_by_website(self, website):
        """Get all sessions for a specific website"""
        return [session for session in self.sessions 
                if session.website and website.lower() in session.website.lower()]
    
    def get_all_sessions(self, sort_by="start_time", reverse=True):
        """Get all sessions, sorted by the specified field"""
        if sort_by == "start_time":
            return sorted(self.sessions, key=lambda s: s.start_time, reverse=reverse)
        elif sort_by == "website":
            return sorted(self.sessions, key=lambda s: s.website.lower() if s.website else "", reverse=reverse)
        elif sort_by == "page_count":
            return sorted(self.sessions, key=lambda s: s.page_count, reverse=reverse)
        elif sort_by == "duration":
            return sorted(self.sessions, 
                         key=lambda s: (s.end_time - s.start_time) if s.end_time else float('inf'), 
                         reverse=reverse)
        return self.sessions

# Create a global instance of the history manager
history_manager = HistoryManager()