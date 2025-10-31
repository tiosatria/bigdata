import os
import sys
import json
from pathlib import Path

# Make sure we can import data_cleaner from dynaclean
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from data_cleaner import ConfigLoader, RecordProcessor


def main():
    root = BASE
    config_path = str(root / 'cleaning_map.yaml')
    input_file = root / 'test_data' / 'input' / 'sample_wp.jsonl'
    out_dir = root / 'test_data' / 'output'
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(input_file, 'r', encoding='utf-8') as f:
        line = f.readline().strip()
    record = json.loads(line)

    # Inject a subheading and additional wrapped images to verify preservation
    html = record['body']['content']['rendered']
    html = "<h2>SubHeading One</h2>" + html
    html += "<p>Wrapped: <a href='https://example.com/img'><img src='https://img.example.com/b.jpg' alt='b'/></a></p>"
    html += "<p>Noscript: <noscript><img src='https://img.example.com/c.jpg' alt='c'/></noscript></p>"
    record['body']['content']['rendered'] = html

    loader = ConfigLoader(config_path)
    processor = RecordProcessor(loader, sitekey='sample_wp')
    result = processor.process_wordpress(record)

    assert result['status'] == 'success', f"Processing failed: {result}"
    data = result['data']
    text = data['text']

    # Assertions: placeholders restored with custom formats (with trailing backslash)
    assert '[Image: https://img.example.com/a.png\\]' in text, 'Custom image format missing (plain)'
    assert '[Image: https://img.example.com/b.jpg\\]' in text, 'Custom image format missing (anchor-wrapped)'
    assert '[Image: https://img.example.com/c.jpg\\]' in text, 'Custom image format missing (noscript)'
    assert '\\begin{tabular}' in text and '\\end{tabular}' in text, 'LaTeX table missing'
    # Heading preserved as plain text (no markdown), single newline
    assert 'SubHeading One\n' in text, 'Subheading not preserved as plain text'
    assert '## SubHeading One' not in text, 'Subheading should not be in markdown'

    # Noise should be removed
    lower = text.lower()
    assert 'breadcrumbs' not in lower, 'Breadcrumbs noise not removed'
    assert '<em>' not in lower, 'Raw <em> tags should not remain'
    assert 'related' not in lower, 'Related posts noise not removed'

    # Write output for manual inspection
    out_path = out_dir / 'sample_wp_cleaned.jsonl'
    with open(out_path, 'w', encoding='utf-8') as out:
        out.write(json.dumps(data, ensure_ascii=False) + '\n')

    print('TEST_OK')


if __name__ == '__main__':
    main()
