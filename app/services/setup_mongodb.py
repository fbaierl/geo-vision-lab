"""
MongoDB Vector Search Index Setup Script

This script initializes MongoDB and creates the necessary vector search index
for the GeoVision Lab RAG system.
"""
import logging
import sys
from app.services.vector_store import ensure_vector_index, get_mongo_client
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mongodb_setup")


def main():
    logger.info("[MONGODB] Setting up MongoDB vector search index...")
    
    try:
        # Test connection
        client = get_mongo_client()
        client.admin.command('ping')
        logger.info("[MONGODB] Connection successful")
        
        # Create vector search index
        ensure_vector_index()
        logger.info(f"[MONGODB] Vector search index '{settings.VECTOR_INDEX_NAME}' created successfully")
        
        logger.info("[MONGODB] Setup complete")
    except Exception as e:
        logger.error(f"[MONGODB] Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
