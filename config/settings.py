"""
Configuration for the KiCad MCP Server.
All settings loaded from environment variables with sensible defaults.
"""

import os

# Path to the local kicad-doc git clone
KICAD_DOC_PATH: str = os.environ.get("KICAD_DOC_PATH", "")

# KiCad documentation version to serve
KICAD_DOC_VERSION: str = os.environ.get("KICAD_DOC_VERSION", "9.0")

# MCP server host
MCP_HOST: str = os.environ.get("MCP_HOST", "127.0.0.1")

# MCP server port
MCP_PORT: int = int(os.environ.get("MCP_PORT", "8080"))

# Directory for tool call log files
LOG_DIR: str = os.environ.get("LOG_DIR", "logs")
