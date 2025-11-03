#!/usr/bin/env python3
"""
REBEL Music Database - Initialization Script
Sets up PostgreSQL database and Qdrant vector store
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from pathlib import Path
import sys

# Configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'rebel'),
    'password': os.getenv('POSTGRES_PASSWORD', 'rebel_password'),
    'database': os.getenv('POSTGRES_DB', 'rebel_music')
}

def create_database():
    """Create database if it doesn't exist"""
    print("🔧 Checking if database exists...")
    
    # Connect to postgres database first
    conn = psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database='postgres'
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Check if database exists
    cursor.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s",
        (DB_CONFIG['database'],)
    )
    
    if not cursor.fetchone():
        print(f"📦 Creating database '{DB_CONFIG['database']}'...")
        cursor.execute(f"CREATE DATABASE {DB_CONFIG['database']}")
        print("✅ Database created")
    else:
        print(f"✓ Database '{DB_CONFIG['database']}' already exists")
    
    cursor.close()
    conn.close()

def run_schema():
    """Execute schema.sql file"""
    print("\n🏗️  Running schema...")
    
    # Connect to the rebel_music database
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Read schema file
    schema_path = Path(__file__).parent / 'schema.sql'
    
    if not schema_path.exists():
        print(f"❌ Error: schema.sql not found at {schema_path}")
        sys.exit(1)
    
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    try:
        cursor.execute(schema_sql)
        conn.commit()
        print("✅ Schema created successfully")
    except psycopg2.Error as e:
        print(f"❌ Error creating schema: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

def verify_tables():
    """Verify all tables were created"""
    print("\n🔍 Verifying tables...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    
    tables = cursor.fetchall()
    
    expected_tables = {
        'tracks',
        'track_links',
        'artists',
        'labels',
        'user_favorites',
        'processing_queue',
        'embeddings',
        'crawl_history'
    }
    
    created_tables = {t[0] for t in tables}
    
    print(f"\n📊 Tables created ({len(created_tables)}):")
    for table in sorted(created_tables):
        print(f"  ✓ {table}")
    
    missing = expected_tables - created_tables
    if missing:
        print(f"\n⚠️  Missing tables: {missing}")
    else:
        print("\n✅ All expected tables created")
    
    cursor.close()
    conn.close()

def setup_qdrant():
    """Initialize Qdrant collection for embeddings"""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        
        print("\n🗄️  Setting up Qdrant vector store...")
        
        qdrant_host = os.getenv('QDRANT_HOST', 'localhost')
        qdrant_port = int(os.getenv('QDRANT_PORT', 6333))
        
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        
        # Create collection for music embeddings
        collection_name = 'music_embeddings'
        
        # Check if collection exists
        try:
            client.get_collection(collection_name)
            print(f"✓ Collection '{collection_name}' already exists")
        except:
            # Create collection
            print(f"📦 Creating collection '{collection_name}'...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=512,  # CLAP embedding size
                    distance=Distance.COSINE
                )
            )
            print("✅ Qdrant collection created")
        
    except ImportError:
        print("\n⚠️  Qdrant client not installed. Skipping vector store setup.")
        print("   Install with: pip install qdrant-client")
    except Exception as e:
        print(f"\n⚠️  Could not connect to Qdrant: {e}")
        print("   Make sure Qdrant is running: docker run -p 6333:6333 qdrant/qdrant")

def print_connection_info():
    """Print connection information"""
    print("\n" + "="*60)
    print("📝 DATABASE CONNECTION INFO")
    print("="*60)
    print(f"Host:     {DB_CONFIG['host']}")
    print(f"Port:     {DB_CONFIG['port']}")
    print(f"Database: {DB_CONFIG['database']}")
    print(f"User:     {DB_CONFIG['user']}")
    print("\nConnection string:")
    print(f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("="*60)

def main():
    """Main initialization function"""
    print("\n" + "="*60)
    print("🎵 REBEL MUSIC DATABASE INITIALIZATION")
    print("="*60 + "\n")
    
    try:
        # Step 1: Create database
        create_database()
        
        # Step 2: Run schema
        run_schema()
        
        # Step 3: Verify tables
        verify_tables()
        
        # Step 4: Setup Qdrant
        setup_qdrant()
        
        # Step 5: Print connection info
        print_connection_info()
        
        print("\n✅ Initialization complete!")
        print("\n📚 Next steps:")
        print("  1. Start crawling: python scrapers/musicbrainz_crawler.py")
        print("  2. Generate embeddings: python processing/embeddings_generator.py")
        print("  3. Start API: python api/main.py")
        
    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
