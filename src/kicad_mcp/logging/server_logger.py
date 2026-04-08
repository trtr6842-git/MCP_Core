"""
Server logging configuration: terminal (INFO) and file (DEBUG).

Provides setup functions for:
- Terminal handler: INFO level, human-readable tool call logs
- File handler: DEBUG level, verbose audit trail with full details
- MCP SDK noise suppression
"""

import logging
import logging.handlers
import os
import time
from pathlib import Path


def configure_logging(log_dir: str | Path) -> None:
    """
    Configure logging for the server.

    Sets up:
    1. Terminal handler (INFO level) for human-readable logs
    2. File handler (DEBUG level) for detailed debugging
    3. Suppresses MCP SDK noise
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, filter at handlers

    # Suppress MCP SDK noise
    logging.getLogger("mcp").setLevel(logging.WARNING)

    # Terminal handler (INFO level, human-readable)
    terminal_handler = logging.StreamHandler()
    terminal_handler.setLevel(logging.INFO)
    terminal_formatter = logging.Formatter(
        "[KiCad MCP] %(message)s"
    )
    terminal_handler.setFormatter(terminal_formatter)
    root_logger.addHandler(terminal_handler)

    # File handler (DEBUG level, detailed)
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{timestamp_str}_server.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)


def get_tool_logger() -> logging.Logger:
    """Get the logger for tool call logging (terminal output)."""
    return logging.getLogger("kicad_mcp.tools")


def get_execution_logger() -> logging.Logger:
    """Get the logger for execution details (file log)."""
    return logging.getLogger("kicad_mcp.execution")
