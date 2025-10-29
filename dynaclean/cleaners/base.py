"""
Base cleaner interface
"""
from abc import ABC, abstractmethod
from utils.logger import get_logger


class BaseCleaner(ABC):
    def __init__(self, params, config):
        self.params = params
        self.config = config
        self.logger = get_logger(f'cleaner.{self.name}')

    @property
    @abstractmethod
    def name(self):
        """Cleaner name"""
        pass

    @abstractmethod
    def clean(self, record):
        """
        Clean a record
        Returns: cleaned record or None if record should be filtered
        """
        pass

    def _get_nested(self, obj, path):
        """Get nested value from object"""
        keys = path.split('.')
        value = obj
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
            if value is None:
                return None
        return value

    def _set_nested(self, obj, path, value):
        """Set nested value in object"""
        keys = path.split('.')
        target = obj
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value