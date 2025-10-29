"""
Anonymization cleaner (basic implementation)
"""
import re
from .base import BaseCleaner


class AnonymizationCleaner(BaseCleaner):
    @property
    def name(self):
        return 'anonymization'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Basic patterns for PII
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.phone_pattern = re.compile(r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b')
        self.ssn_pattern = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')

        # Replacement tokens
        self.email_token = '[EMAIL]'
        self.phone_token = '[PHONE]'
        self.ssn_token = '[SSN]'

    def clean(self, record):
        """Anonymize PII in body"""
        body = record.get('body', '')

        if body:
            # Replace emails
            body = self.email_pattern.sub(self.email_token, body)

            # Replace phone numbers
            body = self.phone_pattern.sub(self.phone_token, body)

            # Replace SSNs
            body = self.ssn_pattern.sub(self.ssn_token, body)

            record['body'] = body

        return record