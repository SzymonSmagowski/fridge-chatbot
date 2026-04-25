import logging
import sys
from typing import Optional


class LoggerService:
    _instance = None
    _logger_name = "fridge_chatbot_backend"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = logging.getLogger(self._logger_name)
        self.configure_logger("INFO")
        self._initialized = True

    def configure_logger(self, log_level: str = "INFO") -> None:
        level = getattr(logging, log_level.upper())
        self.logger.setLevel(level)
        for h in self.logger.handlers[:]:
            self.logger.removeHandler(h)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
            )
        )
        self.logger.addHandler(handler)

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        if name:
            child = logging.getLogger(f"{self._logger_name}.{name}")
            child.propagate = True
            return child
        return self.logger


logger_service = LoggerService()


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logger_service.get_logger(name)
