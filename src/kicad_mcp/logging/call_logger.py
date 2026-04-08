"""
Logs every MCP tool call to a structured JSON lines file.
Fields: timestamp, user, command (raw command string).
"""

import json
import time
from pathlib import Path


class CallLogger:
    """Writes structured JSON log entries for each MCP tool call."""

    def __init__(self, log_dir: Path, user: str) -> None:
        """
        Initialize the logger.

        Args:
            log_dir: Directory where log files are written.
            user: Username associated with this server instance.
        """
        self._user = user
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_calls_{user}.jsonl"
        self._log_path = log_dir / filename
        self._file = open(self._log_path, "a", encoding="utf-8")

    def log_call(self, command: str, latency_ms: float = 0.0, result_count: int = 0) -> None:
        """
        Write a single log entry as a JSON line.

        Args:
            command: The raw command string passed to the kicad tool.
            latency_ms: Execution time in milliseconds.
            result_count: Number of results returned.
        """
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "user": self._user,
            "command": command,
            "latency_ms": latency_ms,
            "result_count": result_count,
        }
        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()
