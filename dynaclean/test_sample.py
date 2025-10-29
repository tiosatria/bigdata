#!/usr/bin/env python3
"""
Test script to validate the pipeline setup
"""
import json
import os
from pathlib import Path


def create_test_data():
    """Create sample test data"""
    # Create test directory structure
    data_root = Path('./test_data')
    input_dir = data_root / 'input'
    output_dir = data_root / 'output'
    logs_dir = data_root / 'logs'

    for d in [input_dir, output_dir, logs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Sample records
    records = [
        {
            'metadata': {
                'title': 'Healthy Eating Tips - Joyous Health',
                'url': 'https://joyoushealth.com/articles/healthy-eating',
                'hostname': 'joyoushealth.com',
                'description': 'Learn about healthy eating',
                'categories': ['health', 'nutrition'],
                'tags': ['wellness', 'diet'],
                'pagetype': 'article',
                'filedate': '2025-10-25',
                'body_type': 'html',
                'sitename': 'Joyous Health',
                'date': '2024-02-11'
            },
            'body': '''
            <html>
            <head><title>Test</title></head>
            <body>
                <nav>Navigation</nav>
                <div class="main-content">
                    <h1>Healthy Eating Tips</h1>
                    <p>Eating healthy is important for maintaining good health. 
                    Here are some tips to help you eat better and feel great.
                    A balanced diet includes fruits, vegetables, whole grains, and lean proteins.
                    Remember to stay hydrated and limit processed foods.</p>
                </div>
                <footer>Copyright 2024</footer>
            </body>
            </html>
            '''
        },
        {
            'metadata': {
                'title': 'Contact Us',
                'url': 'https://joyoushealth.com/contact',
                'hostname': 'joyoushealth.com',
                'description': 'Contact page',
                'categories': ['info'],
                'tags': ['contact'],
                'pagetype': 'page',
                'filedate': '2025-10-25',
                'body_type': 'html',
                'sitename': 'Joyous Health',
                'date': '2024-02-11'
            },
            'body': '<html><body><h1>Contact Us</h1><p>Email us at contact@example.com</p></body></html>'
        },
        {
            'metadata': {
                'title': 'Another Great Article',
                'url': 'https://joyoushealth.com/articles/another-article',
                'hostname': 'joyoushealth.com',
                'description': 'Another article',
                'categories': ['lifestyle'],
                'tags': ['wellness'],
                'pagetype': 'article',
                'filedate': '2025-10-25',
                'body_type': 'html',
                'sitename': 'Joyous Health',
                'date': '2024-03-15'
            },
            'body': '''
            <html><body>
            <h1>Another Great Article</h1>
            <p>This is another informative article with plenty of content to meet the minimum length requirements.
            We discuss various topics related to health and wellness in this comprehensive guide.
            The content is designed to be helpful and informative for our readers.</p>
            </body></html>
            '''
        }
    ]

    # Write test file
    test_file = input_dir / 'joyoushealth_test_data.jsonl'
    with open(test_file, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    print(f"✓ Test data created at {test_file}")
    print(f"✓ Created {len(records)} test records")

    # Set environment variable
    os.environ['DATA_ROOT'] = str(data_root.absolute())
    print(f"✓ Set DATA_ROOT={os.environ['DATA_ROOT']}")

    return data_root


def validate_setup():
    """Validate that all required modules can be imported"""
    try:
        import yaml
        print("✓ PyYAML installed")
    except ImportError:
        print("✗ PyYAML not installed. Run: pip install PyYAML")
        return False

    try:
        import tqdm
        print("✓ tqdm installed")
    except ImportError:
        print("✗ tqdm not installed. Run: pip install tqdm")
        return False

    try:
        import trafilatura
        print("✓ trafilatura installed")
    except ImportError:
        print("⚠ trafilatura not installed (optional). Run: pip install trafilatura")

    try:
        import lxml
        print("✓ lxml installed")
    except ImportError:
        print("✗ lxml not installed. Run: pip install lxml")
        return False

    # Check if all pipeline modules exist
    required_files = [
        'orchestrator.py',
        'config_loader.py',
        'key_mapper.py',
        'cleaners/__init__.py',
        'processors/__init__.py',
        'utils/__init__.py',
        'site_cfg.yaml'
    ]

    all_exist = True
    for f in required_files:
        if Path(f).exists():
            print(f"✓ {f} exists")
        else:
            print(f"✗ {f} missing")
            all_exist = False

    return all_exist


if __name__ == '__main__':
    print("=" * 60)
    print("Pipeline Setup Validation")
    print("=" * 60)

    print("\n1. Checking dependencies...")
    if not validate_setup():
        print("\n✗ Setup validation failed. Please install missing dependencies.")
        exit(1)

    print("\n2. Creating test data...")
    data_root = create_test_data()

    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print("\nTo run the pipeline on test data:")
    print(f"  export DATA_ROOT={data_root.absolute()}")
    print("  python orchestrator.py")
    print("\nExpected results:")
    print("  - 1 record should pass (healthy eating article)")
    print("  - 1 record should be filtered (contact page - URL filter)")
    print("  - 1 record may be filtered (short content)")
    print(f"\nCheck output at: {data_root / 'output'}")
    print(f"Check logs at: {data_root / 'logs'}")