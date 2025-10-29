# JSONL Data Cleaning Pipeline

A modular, scalable pipeline for cleaning and processing JSONL data with configurable site-specific rules.

## Features

- **Multi-site Configuration**: Global defaults with per-site overrides
- **Parallel Processing**: Multi-worker support for large datasets
- **Modular Cleaning Pipeline**: Extensible cleaner framework
- **Advanced Filtering**: Include/exclude patterns with regex support
- **URL Deduplication**: Automatic duplicate detection
- **Progress Tracking**: File-level and record-level progress bars
- **Comprehensive Logging**: Multi-level logging (console, file, errors)

## Installation

```bash
pip install -r requirements.txt
```

## Project Structure

```
project/
├── orchestrator.py              # Main entry point
├── config_loader.py             # YAML config parser
├── key_mapper.py                # Dynamic key mapping
├── site_cfg.yaml                # Configuration file
├── requirements.txt
├── cleaners/
│   ├── __init__.py
│   ├── base.py                  # Base cleaner class
│   ├── url_dedupe.py
│   ├── html_body.py
│   ├── emoji.py
│   ├── anonymization.py
│   ├── non_latin.py
│   ├── whitespace.py
│   ├── zero_width_space.py
│   ├── html_unescape.py
│   ├── title_site_template.py
│   └── english_only.py
├── processors/
│   ├── __init__.py
│   ├── deduplicator.py
│   ├── filter.py
│   └── validator.py
└── utils/
    ├── __init__.py
    ├── logger.py
    └── helpers.py
```

## Usage

### Basic Usage

```bash
python orchestrator.py
```

### Custom Config Path

```bash
python orchestrator.py -c /path/to/custom_config.yaml
```

## Configuration

### File Naming Convention

Files are mapped to site configurations based on filename:

```
example_com_deduped.jsonl => site key: "example"
joyoushealth_com_raw.jsonl => site key: "joyoushealth"
```

The site key is extracted by splitting the filename by `_` and taking the first part.

### YAML Structure

See `site_cfg.yaml` for complete configuration options:

- **GLOBAL**: Default settings applied to all sites
- **SITES**: Site-specific configurations with inheritance
  - Use `inherit: GLOBAL` to inherit global settings
  - Use `overrides` to customize specific settings

### Key Mapping Syntax

The key mapper supports several special syntaxes:

- `<uuid4>`: Generate new UUID
- `@value`: Static literal value
- `<field1>\n<field2>`: Concatenate with newline
- `field[:first]` / `field[:last]`: Array indexing
- `option1 or option2 or fallback`: Fallback chain
- `<meta.path.to.field>`: Reference to output fields

Example:
```yaml
text: <title>\n<body>  # Concatenates title and body
domain: metadata.categories[:first] or metadata.tags[:last] or <meta.content_info.fallbacks.domain>
```

## Processing Flow

```
1. Load YAML config
2. Scan input directory for JSONL files
3. Extract site key from filename
4. For each file (parallel):
   a. Load records
   b. Deduplicate by URL
   c. Apply exclude filters
   d. Apply include filters
   e. Run cleaning pipeline (sequential)
   f. Map to output schema
   g. Validate text length
   h. Write to output
5. Aggregate statistics
```

## Cleaning Pipeline

### Available Cleaners

1. **url_dedupe_and_filtering**: Filter URLs by regex patterns
2. **html_body_cleaning**: Extract clean text from HTML (uses trafilatura)
3. **emoji_cleaning**: Remove emoji characters
4. **anonymization**: Redact PII (emails, phones, SSNs)
5. **non_latin**: Remove non-Latin characters
6. **whitespace**: Normalize whitespace
7. **zero_width_space**: Remove zero-width characters
8. **html_unescape**: Unescape HTML entities
9. **title_site_template**: Remove site name from titles
10. **english_only_filter**: Filter non-English content

### Adding Custom Cleaners

1. Create a new cleaner class inheriting from `BaseCleaner`
2. Implement `name` property and `clean` method
3. Register in `cleaners/__init__.py`

Example:

```python
from .base import BaseCleaner

class CustomCleaner(BaseCleaner):
    @property
    def name(self):
        return 'custom_cleaner'
    
    def clean(self, record):
        # Your cleaning logic
        return record
```

## Filtering

### Exclude Filters

Records matching ANY exclude pattern are filtered out:

```yaml
filters:
  exclude:
    url:
      - "(?i)about"
      - "(?i)contact"
    domain:
      - "(?i)news"
```

### Include Filters

When specified, only records matching ALL include patterns are kept:

```yaml
filters:
  include:
    url:
      - "(?i)article"
    domain:
      - "(?i)health"
```

**Note**: Exclude takes precedence over include.

## Environment Variables

Set `DATA_ROOT` environment variable for dynamic paths:

```bash
export DATA_ROOT=/path/to/data
```

Paths in config can use `${DATA_ROOT}`:

```yaml
paths:
  input: "${DATA_ROOT}/input"
  output: "${DATA_ROOT}/output"
```

## Output Format

```jsonl
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "text": "Title\nCleaned body text...",
  "meta": {
    "data_info": {
      "url": "https://example.com/article",
      "lang": "en",
      "source": "Example Site",
      "type": "article",
      "processing_date": "2024-02-11",
      "delivery_version": "v1",
      "title": "Article Title"
    },
    "content_info": {
      "domain": "health",
      "subdomain": "nutrition"
    }
  }
}
```

## Logging

Three log files are generated per run:

- `pipeline_TIMESTAMP.log`: All events (DEBUG and above)
- `errors_TIMESTAMP.log`: Errors only
- Console output: INFO and above

## Statistics

Final output includes:

- Total records processed
- Deduplicated count
- Filtered counts (exclude, include, validation)
- Successfully processed count
- Errors

## Performance

- **Workers**: Configurable parallel processing (default: 12)
- **Memory**: Deduplication uses in-memory set (reset per file)
- **Progress**: Real-time progress bars for files and records

## Troubleshooting

### Trafilatura Not Installed

If trafilatura is not available, the pipeline falls back to lxml-based cleaning.

### Missing Site Config

If a site key is not found in YAML, the pipeline uses the `default` config, or falls back to `GLOBAL`.

### Large Files

For very large JSONL files, consider:
- Splitting files into smaller chunks
- Reducing worker count if memory is limited
- Monitoring log files for bottlenecks

## Extension Points

The pipeline is designed for easy extension:

1. **Custom Cleaners**: Add new cleaner classes
2. **Custom Filters**: Extend Filter class with new logic
3. **Custom Key Mapping**: Extend KeyMapper with new syntax
4. **Custom Validation**: Add rules to Validator

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]