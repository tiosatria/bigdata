"""
Helper utilities
"""
import uuid
from pathlib import Path
from datetime import datetime


def extract_site_key(filename):
    """
    Extract site key from filename
    Convention: filename => site key (split by '_' and get first part)
    Example: example_com_deduped => example
    """
    parts = filename.split('_')
    if parts:
        return parts[0]
    return 'default'


def ensure_dir(path):
    """Ensure directory exists"""
    Path(path).mkdir(parents=True, exist_ok=True)


def generate_uuid():
    """Generate UUID4"""
    return str(uuid.uuid4())


def parse_date(date_str):
    """Parse date string to ISO format"""
    if not date_str:
        return None

    # Try common formats
    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%d/%m/%Y',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    # Return original if parsing fails
    return date_str


def safe_get(obj, path, default=None):
    """Safely get nested value from dict"""
    keys = path.split('.')
    value = obj

    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return default

        if value is None:
            return default

    return value