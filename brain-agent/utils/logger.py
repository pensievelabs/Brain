import logging
import os
from datetime import date
from config import Config

class DailyFileHandler(logging.FileHandler):
    """
    A custom file handler that dynamically switches files at midnight.
    Always writes to a file named with the current date.
    """
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.current_date = date.today().isoformat()
        os.makedirs(self.log_dir, exist_ok=True)
        super().__init__(self._get_filename(), encoding="utf-8")
        
    def _get_filename(self) -> str:
        return os.path.join(self.log_dir, f"brain_agent_{self.current_date}.log")
        
    def emit(self, record):
        new_date = date.today().isoformat()
        if self.current_date != new_date:
            self.current_date = new_date
            self.close()
            self.baseFilename = os.path.abspath(self._get_filename())
            self.stream = self._open()
        super().emit(record)

def get_logger(name: str) -> logging.Logger:
    """
    Returns a configured logger that writes to a daily rotating file in logs/.
    Logs format: [TIMESTAMP] [NAME] [LEVEL]: Message
    Files are named like brain_agent_YYYY-MM-DD.log
    """
    logger = logging.getLogger(name)
    
    # Do not add multiple handlers if logger is already configured
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    
    config = Config()
    log_dir = os.path.join(config.AGENT_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Use our custom handler to cleanly create brain_agent_YYYY-MM-DD.log
    file_handler = DailyFileHandler(log_dir)
    
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    
    # Also add standard output for the console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Prevent propagation to the root logger which might double-log
    logger.propagate = False
    
    return logger
