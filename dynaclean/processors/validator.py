"""
Output record validator
"""
from utils.logger import get_logger


class Validator:
    def __init__(self, config):
        self.config = config
        self.validation = config.get('validation', {})
        self.min_text_length = self.validation.get('min_text_length', 200)
        self.logger = get_logger('validator')

    def validate(self, record):
        """
        Validate output record
        Returns: True if valid, False otherwise
        """
        # Check text field length
        text = record.get('text', '')
        if not text:
            self.logger.debug("Validation failed: empty text field")
            return False

        text_length = len(text.strip())
        if text_length < self.min_text_length:
            self.logger.debug(f"Validation failed: text length {text_length} < {self.min_text_length}")
            return False

        # Check required fields
        if 'id' not in record or not record['id']:
            self.logger.debug("Validation failed: missing id")
            return False

        return True