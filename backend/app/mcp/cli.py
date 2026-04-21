#!/usr/bin/env python3
"""
NightMend MCP Server CLI

Standalone MCP server for NightMend operational tools.
Can be run independently or integrated with the main application.

Usage:
    python -m app.mcp.cli [--host HOST] [--port PORT]
    
Example:
    python -m app.mcp.cli --host 0.0.0.0 --port 8003
"""
import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.mcp.server import start_mcp_server, stop_mcp_server


def setup_logging():
    """Setup logging for MCP server"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='NightMend MCP Server')
    parser.add_argument(
        '--host', 
        default='127.0.0.1', 
        help='Host to bind the server to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port', 
        type=int, 
        default=8003, 
        help='Port to bind the server to (default: 8003)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    setup_logging()
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting NightMend MCP Server on {args.host}:{args.port}")
    
    try:
        # Check database connection
        from sqlalchemy import text
        from app.core.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("Database connection verified")
        
        # Start the server
        start_mcp_server(host=args.host, port=args.port)
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        stop_mcp_server()
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()