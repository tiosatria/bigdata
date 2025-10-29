"""
Dynamic key mapping engine with fallback support
"""
import re
import uuid
from datetime import datetime
from utils.logger import get_logger


class KeyMapper:
    def __init__(self, config):
        self.config = config
        self.key_mapping = config.get('key_mapping', {})
        self.meta_config = config.get('meta', {})
        self.logger = get_logger('key_mapper')

    def map(self, record):
        """Map input record to output schema"""
        output = {}

        for key, mapping in self.key_mapping.items():
            output[key] = self._resolve_value(mapping, record, output)

        return output

    def _resolve_value(self, mapping, record, output, depth=0):
        """Recursively resolve mapping value"""
        if depth > 10:
            self.logger.warning("Maximum recursion depth reached in key mapping")
            return None

        if isinstance(mapping, dict):
            # Nested object
            result = {}
            for k, v in mapping.items():
                result[k] = self._resolve_value(v, record, output, depth + 1)
            return result

        elif isinstance(mapping, str):
            # String mapping - parse and resolve
            return self._parse_mapping_string(mapping, record, output, depth)

        else:
            # Literal value
            return mapping

    def _parse_mapping_string(self, mapping, record, output, depth):
        """Parse mapping string with various syntax support"""
        mapping = mapping.strip()

        # Handle <uuid4>
        if mapping == '<uuid4>':
            return str(uuid.uuid4())

        if mapping == '<now>':
            return datetime.now().isoformat()

        # Handle static literals with @
        if mapping.startswith('@'):
            return mapping[1:]

        # Handle concatenation with \n
        if '\\n' in mapping:
            parts = mapping.split('\\n')
            values = []
            for part in parts:
                part = part.strip('<>').strip()
                val = self._resolve_field_path(part, record, output, depth)
                if val:
                    values.append(str(val))
            return '\n'.join(values) if values else None

        # Handle reference to output field <meta.content_info.specify.domain>
        if mapping.startswith('<') and mapping.endswith('>'):
            ref_path = mapping.strip('<>')
            return self._resolve_field_path(ref_path, record, output, depth)

        # Handle fallback chain with 'or'
        if ' or ' in mapping:
            return self._resolve_fallback_chain(mapping, record, output, depth)

        # Simple field path
        return self._resolve_field_path(mapping, record, output, depth)

    def _resolve_fallback_chain(self, chain, record, output, depth):
        """Resolve fallback chain: option1 or option2 or option3"""
        options = [opt.strip() for opt in chain.split(' or ')]

        for option in options:
            value = self._parse_mapping_string(option, record, output, depth + 1)
            if value is not None and value != '':
                return value

        return None

    def _resolve_field_path(self, path, record, output, depth):
        """Resolve field path with array indexing support"""
        # Handle array indexing [:first] or [:last]
        array_index = None
        if '[:first]' in path:
            path = path.replace('[:first]', '')
            array_index = 'first'
        elif '[:last]' in path:
            path = path.replace('[:last]', '')
            array_index = 'last'

        # Navigate path
        keys = path.split('.')

        # Check if referencing output or record
        if keys[0] == 'meta' and depth > 0:
            # Reference to output/meta
            value = self._get_nested(output, keys)
        else:
            # Reference to input record
            value = self._get_nested(record, keys)

        # Apply array indexing
        if array_index and isinstance(value, list) and len(value) > 0:
            if array_index == 'first':
                return value[0]
            elif array_index == 'last':
                return value[-1]

        # Get fallback if value is None
        if value is None or value == '':
            fallback = self._get_fallback(path)
            return fallback

        return value

    def _get_nested(self, obj, keys):
        """Get nested value from object"""
        value = obj
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
            if value is None:
                return None
        return value

    def _get_fallback(self, path):
        """Get fallback value from meta config"""
        # Extract the last part of the path for fallback lookup
        keys = path.split('.')

        # Try to find in fallbacks
        if len(keys) >= 2:
            section = keys[0]  # e.g., 'data_info', 'content_info'
            field = keys[-1]  # e.g., 'lang', 'domain'

            # Navigate meta config
            if section in ['data_info', 'content_info']:
                fallback_path = f"meta.{section}.fallbacks.{field}"
                return self._get_nested(self.config, fallback_path.split('.'))

        return None