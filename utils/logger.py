import logging
import contextvars
from datetime import datetime

# Context variable to hold request_id globally in the thread/task
request_id_var = contextvars.ContextVar("request_id", default="")

# ANSI escape codes for terminal coloring
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"


class ColoredFormatter(logging.Formatter):
    """Custom logging formatter to add colors and dynamically inject Request ID."""

    COLORS = {
        logging.DEBUG: BLUE,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: RED + BOLD,
    }

    def format(self, record):
        level_color = self.COLORS.get(record.levelno, WHITE)
        level_name = f"{level_color}{record.levelname:<7}{RESET}"
        
        # Resolve request_id from contextvar
        req_id = request_id_var.get()
        req_str = f"[{CYAN}Request ID: {req_id}{RESET}] " if req_id else ""
        
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Store original message to avoid mutating it permanently on multiple format calls
        orig_msg = record.msg
        record.msg = f"{WHITE}[{timestamp}]{RESET} {level_name} {req_str}{record.msg}"
        formatted = super().format(record)
        record.msg = orig_msg  # Restore
        
        return formatted


# Initialize Logger
logger = logging.getLogger("trendly")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = ColoredFormatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
