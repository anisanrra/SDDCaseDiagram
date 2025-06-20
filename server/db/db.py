import sqlite3
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json


class DatabaseManager:
    """Main database manager class for user management system with authentication."""
    
    def __init__(self, db_path: str = "user_management.db"):
        """Initialize the database manager.
        
        Args:
            db_path (str): Path to the SQLite database file
        """
        self.db_path = db_path
        self.connection = None
        self.connect()
        self.create_tables()
        self.create_default_roles_and_permissions()
    
    def connect(self) -> None:
        """Establish connection to the SQLite database."""
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row  # Enable dict-like access to rows
            self.connection.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
            print(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            print(f"Error connecting to database: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            print("Database connection closed")
    
    def execute_query(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query with parameters.
        
        Args:
            query (str): SQL query to execute
            params (tuple): Parameters for the query
            
        Returns:
            sqlite3.Cursor: Cursor object with query results
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            self.connection.commit()
            return cursor
        except sqlite3.Error as e:
            print(f"Error executing query: {e}")
            self.connection.rollback()
            raise
    
    def create_tables(self) -> None:
        """Create all database tables."""
        
        # Users table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                email_verified BOOLEAN DEFAULT 0,
                password_hash VARCHAR(255) NOT NULL,
                salt VARCHAR(255),
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                avatar_url VARCHAR(500),
                bio TEXT,
                is_active BOOLEAN DEFAULT 1,
                is_deleted BOOLEAN DEFAULT 0,
                current_results INTEGER,
                last_login_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for users
        self.execute_query("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        self.execute_query("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_users_active_deleted ON users(is_active, is_deleted)")
        
        # User sessions table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id VARCHAR(255) PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_info VARCHAR(500),
                ip_address VARCHAR(45),
                is_active BOOLEAN DEFAULT 1,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_sessions_user_active ON user_sessions(user_id, is_active)")
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at)")
        
        # Password reset tokens
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        self.execute_query("CREATE UNIQUE INDEX IF NOT EXISTS idx_reset_token ON password_reset_tokens(token)")
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_reset_user_expires ON password_reset_tokens(user_id, expires_at)")
        
        # Email verification tokens
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                verified_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        self.execute_query("CREATE UNIQUE INDEX IF NOT EXISTS idx_email_verify_token ON email_verification_tokens(token)")
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_email_verify_user_expires ON email_verification_tokens(user_id, expires_at)")
        
        # Roles table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Permissions table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                resource VARCHAR(100),
                action VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Role permissions junction table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER,
                permission_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
            )
        """)
        
        # User roles junction table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER,
                role_id INTEGER,
                assigned_by INTEGER,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_by) REFERENCES users(id)
            )
        """)
        
        # Security audit log
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS user_security_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type VARCHAR(100) NOT NULL,
                ip_address VARCHAR(45),
                user_agent VARCHAR(500),
                success BOOLEAN DEFAULT 1,
                failure_reason VARCHAR(255),
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_security_logs_user_date ON user_security_logs(user_id, created_at)")
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_security_logs_event_date ON user_security_logs(event_type, created_at)")
        
        # Friends table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_user_id INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                requested_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, friend_user_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (friend_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_friends_status ON friends(friend_user_id, status)")
        
        # Results table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                extraversion REAL,
                agreeableness REAL,
                conscientiousness REAL,
                emotional_stability REAL,
                intellect_imagination REAL,
                test_version VARCHAR(50),
                is_current BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_results_user_current ON results(user_id, is_current)")
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_results_user_date ON results(user_id, created_at)")
        
        # Posts table
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(255) NOT NULL,
                body TEXT,
                user_id INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'draft',
                visibility VARCHAR(20) DEFAULT 'public',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_posts_user_status ON posts(user_id, status)")
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_posts_status_visibility_date ON posts(status, visibility, created_at)")
        
        # Add foreign key constraint for current_results
        self.execute_query("""
            CREATE TRIGGER IF NOT EXISTS fk_users_current_results
            BEFORE UPDATE OF current_results ON users
            FOR EACH ROW
            WHEN NEW.current_results IS NOT NULL
            BEGIN
                SELECT CASE
                    WHEN (SELECT id FROM results WHERE id = NEW.current_results) IS NULL
                    THEN RAISE(ABORT, 'Foreign key constraint failed: current_results')
                END;
            END
        """)
        
        print("All tables created successfully")
    
    def create_default_roles_and_permissions(self) -> None:
        """Create default roles and permissions."""
        # Default roles
        default_roles = [
            ('admin', 'Full system administrator'),
            ('moderator', 'Content moderation privileges'),
            ('user', 'Standard user privileges'),
            ('premium_user', 'Premium user with extended features')
        ]
        
        for role_name, description in default_roles:
            try:
                self.execute_query(
                    "INSERT OR IGNORE INTO roles (name, description) VALUES (?, ?)",
                    (role_name, description)
                )
            except sqlite3.Error:
                pass  # Role already exists
        
        # Default permissions
        default_permissions = [
            ('create_posts', 'Create new posts', 'posts', 'create'),
            ('edit_posts', 'Edit posts', 'posts', 'update'),
            ('delete_posts', 'Delete posts', 'posts', 'delete'),
            ('view_posts', 'View posts', 'posts', 'read'),
            ('manage_users', 'Manage user accounts', 'users', 'manage'),
            ('view_profiles', 'View user profiles', 'users', 'read'),
            ('take_personality_test', 'Take personality assessments', 'results', 'create'),
            ('view_results', 'View personality results', 'results', 'read')
        ]
        
        for perm_name, description, resource, action in default_permissions:
            try:
                self.execute_query(
                    "INSERT OR IGNORE INTO permissions (name, description, resource, action) VALUES (?, ?, ?, ?)",
                    (perm_name, description, resource, action)
                )
            except sqlite3.Error:
                pass  # Permission already exists
        
        print("Default roles and permissions created")
    
    def hash_password(self, password: str, salt: str = None) -> tuple:
        """Hash a password with salt.
        
        Args:
            password (str): Plain text password
            salt (str): Optional salt, generates new one if not provided
            
        Returns:
            tuple: (hashed_password, salt)
        """
        if salt is None:
            salt = secrets.token_hex(32)
        
        # Use PBKDF2 for password hashing
        password_hash = hashlib.pbkdf2_hmac('sha256', 
                                          password.encode('utf-8'), 
                                          salt.encode('utf-8'), 
                                          100000)  # 100,000 iterations
        
        return password_hash.hex(), salt
    
    def verify_password(self, password: str, stored_hash: str, salt: str) -> bool:
        """Verify a password against stored hash.
        
        Args:
            password (str): Plain text password to verify
            stored_hash (str): Stored password hash
            salt (str): Salt used for hashing
            
        Returns:
            bool: True if password matches
        """
        password_hash, _ = self.hash_password(password, salt)
        return password_hash == stored_hash
    
    def create_user(self, username: str, email: str, password: str, 
                   first_name: str = None, last_name: str = None) -> Optional[int]:
        """Create a new user.
        
        Args:
            username (str): Unique username
            email (str): User email address
            password (str): Plain text password
            first_name (str): Optional first name
            last_name (str): Optional last name
            
        Returns:
            Optional[int]: User ID if successful, None otherwise
        """
        try:
            password_hash, salt = self.hash_password(password)
            
            cursor = self.execute_query("""
                INSERT INTO users (username, email, password_hash, salt, first_name, last_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (username, email, password_hash, salt, first_name, last_name))
            
            user_id = cursor.lastrowid
            
            # Assign default user role
            self.assign_role_to_user(user_id, 'user', user_id)
            
            # Log user creation
            self.log_security_event(user_id, 'user_created', success=True)
            
            print(f"User created successfully with ID: {user_id}")
            return user_id
            
        except sqlite3.IntegrityError as e:
            print(f"Error creating user: {e}")
            return None
    
    def assign_role_to_user(self, user_id: int, role_name: str, assigned_by: int) -> bool:
        """Assign a role to a user.
        
        Args:
            user_id (int): User ID
            role_name (str): Name of the role to assign
            assigned_by (int): ID of user assigning the role
            
        Returns:
            bool: True if successful
        """
        try:
            # Get role ID
            cursor = self.execute_query("SELECT id FROM roles WHERE name = ?", (role_name,))
            role_row = cursor.fetchone()
            
            if not role_row:
                print(f"Role '{role_name}' not found")
                return False
            
            role_id = role_row['id']
            
            self.execute_query("""
                INSERT OR REPLACE INTO user_roles (user_id, role_id, assigned_by)
                VALUES (?, ?, ?)
            """, (user_id, role_id, assigned_by))
            
            return True
            
        except sqlite3.Error as e:
            print(f"Error assigning role: {e}")
            return False
    
    def create_session(self, user_id: int, device_info: str = None, 
                      ip_address: str = None, duration_hours: int = 24) -> str:
        """Create a new user session.
        
        Args:
            user_id (int): User ID
            device_info (str): Device/browser information
            ip_address (str): User's IP address
            duration_hours (int): Session duration in hours
            
        Returns:
            str: Session token
        """
        session_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(hours=duration_hours)
        
        self.execute_query("""
            INSERT INTO user_sessions (id, user_id, device_info, ip_address, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, user_id, device_info, ip_address, expires_at))
        
        # Update last login
        self.execute_query(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,)
        )
        
        # Log login
        self.log_security_event(user_id, 'login', ip_address=ip_address, success=True)
        
        return session_id
    
    def log_security_event(self, user_id: int, event_type: str, 
                          ip_address: str = None, user_agent: str = None,
                          success: bool = True, failure_reason: str = None,
                          metadata: Dict[str, Any] = None) -> None:
        """Log a security event.
        
        Args:
            user_id (int): User ID
            event_type (str): Type of event (login, logout, password_change, etc.)
            ip_address (str): IP address
            user_agent (str): User agent string
            success (bool): Whether the event was successful
            failure_reason (str): Reason for failure if applicable
            metadata (dict): Additional event data
        """
        metadata_json = json.dumps(metadata) if metadata else None
        
        self.execute_query("""
            INSERT INTO user_security_logs 
            (user_id, event_type, ip_address, user_agent, success, failure_reason, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, event_type, ip_address, user_agent, success, failure_reason, metadata_json))
    
    def get_user_by_email(self, email: str) -> Optional[sqlite3.Row]:
        """Get user by email address.
        
        Args:
            email (str): Email address
            
        Returns:
            Optional[sqlite3.Row]: User row if found
        """
        cursor = self.execute_query(
            "SELECT * FROM users WHERE email = ? AND is_active = 1 AND is_deleted = 0",
            (email,)
        )
        return cursor.fetchone()
    
    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user with email and password.
        
        Args:
            email (str): User email
            password (str): Plain text password
            
        Returns:
            Optional[Dict]: User data if authentication successful
        """
        user = self.get_user_by_email(email)
        
        if not user:
            self.log_security_event(None, 'login_failed', 
                                  failure_reason='User not found')
            return None
        
        if self.verify_password(password, user['password_hash'], user['salt']):
            return dict(user)
        else:
            self.log_security_event(user['id'], 'login_failed', 
                                  failure_reason='Invalid password')
            return None
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions.
        
        Returns:
            int: Number of sessions cleaned up
        """
        cursor = self.execute_query(
            "DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP"
        )
        return cursor.rowcount
    
    def get_database_stats(self) -> Dict[str, int]:
        """Get basic database statistics.
        
        Returns:
            Dict[str, int]: Statistics about table row counts
        """
        stats = {}
        tables = ['users', 'user_sessions', 'roles', 'permissions', 
                 'friends', 'results', 'posts', 'user_security_logs']
        
        for table in tables:
            cursor = self.execute_query(f"SELECT COUNT(*) as count FROM {table}")
            stats[table] = cursor.fetchone()['count']
        
        return stats


if __name__ == "__main__":
    """Main function to demonstrate the database system."""

    # parse arg positional arguments
    import argparse
    parser = argparse.ArgumentParser(description="Initialize the Friend Finder Database System")
    parser.add_argument('--db', type=str, default='freind-finder.db',
                        help='Path to the SQLite database file')
    
    args = parser.parse_args()
    
    # Initialize database
    db = DatabaseManager(args.db)
    
    try:
        print("\n=== Database System Initialized ===")
        
        # Create some sample users
        print("\n=== Creating Sample Users ===")
        user1_id = db.create_user("johndoe", "john@example.com", "password123", 
                                 "John", "Doe")
        user2_id = db.create_user("janedoe", "jane@example.com", "securepass456", 
                                 "Jane", "Doe")
        
        if user1_id and user2_id:
            # Create sessions
            print("\n=== Creating Sessions ===")
            session1 = db.create_session(user1_id, "Chrome/Windows", "192.168.1.100")
            session2 = db.create_session(user2_id, "Safari/macOS", "192.168.1.101")
            print(f"Session created for user {user1_id}: {session1}")
            print(f"Session created for user {user2_id}: {session2}")
            
            # Test authentication
            print("\n=== Testing Authentication ===")
            auth_result = db.authenticate_user("john@example.com", "password123")
            if auth_result:
                print(f"Authentication successful for user: {auth_result['username']}")
            
            # Assign admin role to first user
            print("\n=== Assigning Roles ===")
            db.assign_role_to_user(user1_id, "admin", user1_id)
            print(f"Admin role assigned to user {user1_id}")
        
        # Show database statistics
        print("\n=== Database Statistics ===")
        stats = db.get_database_stats()
        for table, count in stats.items():
            print(f"{table}: {count} records")
        
        # Cleanup expired sessions
        print("\n=== Cleaning Up ===")
        cleaned = db.cleanup_expired_sessions()
        print(f"Cleaned up {cleaned} expired sessions")
        
    except Exception as e:
        print(f"Error in main: {e}")
    
    finally:
        # Close database connection
        db.disconnect()