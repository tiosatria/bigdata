#!/usr/bin/env python3
"""
Quick test script for the data cleaning pipeline
Creates a sample input file and tests the pipeline
"""

import json
from pathlib import Path
import subprocess
import sys


def create_test_data():
    """Create sample test data"""
    test_dir = Path('./test_data')
    input_dir = test_dir / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)

    # Sample WordPress record (based on your provided example)
    sample_record = {
        "url": "https://mindoverclutter.ca/unlock-happiness-organize-your-life-now/",
        "id": "a95df1b0-6d48-4c3c-a8ca-65927d9c9f33",
        "meta": {
            "site": "mindoverclutter.ca",
            "body_type": "json/wordpress"
        },
        "body": json.dumps({
            "id": 38682,
            "title": {"rendered": "Unlock Happiness: Organize Your Life Now!"},
            "content": {
                "rendered": "<p>This is a test article about organizing and happiness. It contains enough content to pass the minimum length requirement. Organizing your life can bring joy and reduce stress. Simple habits like journaling, planning ahead, and surrounding yourself with positive people can make a significant difference in your daily happiness.</p><p>Remember that happiness comes from within, and by organizing your space and time, you create room for the things that truly matter. Start small with one area of your life and build from there.</p>"},
            "categories": [229],
            "tags": [419, 439, 265],
            "class_list": ["post-38682", "category-mindset", "tag-happiness"]
        })
    }

    # Create test file
    test_file = input_dir / 'mindoverclutter_ca.jsonl'
    with open(test_file, 'w') as f:
        # Write multiple records
        for i in range(10):
            record = sample_record.copy()
            record['id'] = f"test-id-{i}"
            record['url'] = f"https://mindoverclutter.ca/test-post-{i}/"
            f.write(json.dumps(record) + '\n')

    print(f"✓ Created test file: {test_file}")
    print(f"  Records: 10")
    return test_dir


def create_minimal_config(test_dir):
    """Create minimal configuration file"""
    config_file = test_dir / 'cleaning_map.yaml'

    config_content = """
template_wordpress:
  delivery_version: v1
  domain_fallback: 'daily life'
  subdomain_fallback: 'living'
  type_fallback: 'article'

  pre_filter:
    re_url:
      - '/contact/'
      - '/about/'
    body_length: 100  # Lower threshold for testing

  clean:
    enabled:
      - clean_html
      - clean_title
      - clean_emoji
      - clean_whitespace
      - anonymization
      - clean_punctuation
      - english_only

    args:
      body_xpath: null
      noises:
        - //script
        - //aside
      formating:
        retain_table: true
        retain_image: true

  post_filter:
    re_cleaned_text: []
    re_title: []
    domain_containing: []
    subdomain_containing: []

domain_mapping:
  mindoverclutter.ca:
    domain: 'lifestyle'
    subdomain: 'organizing'

site_mapping:
  mindoverclutter_ca:
    delivery_version: v1
    clean:
      type: 'template_wordpress'
"""

    with open(config_file, 'w') as f:
        f.write(config_content)

    print(f"✓ Created config file: {config_file}")
    return config_file


def run_test():
    """Run the test"""
    print("\n" + "=" * 70)
    print("DATA CLEANING PIPELINE - TEST MODE")
    print("=" * 70 + "\n")

    # Create test data
    test_dir = create_test_data()
    config_file = create_minimal_config(test_dir)

    # Setup directories
    output_dir = test_dir / 'output'
    failed_dir = test_dir / 'failed'
    log_dir = test_dir / 'logs'

    print(f"\nTest directory structure:")
    print(f"  Input:  {test_dir / 'input'}")
    print(f"  Output: {output_dir}")
    print(f"  Failed: {failed_dir}")
    print(f"  Logs:   {log_dir}")

    # Run pipeline
    print("\n" + "-" * 70)
    print("Running pipeline...")
    print("-" * 70 + "\n")

    script_path = Path(__file__).parent / 'data_cleaner.py'
    cmd = [
        sys.executable,
        str(script_path),
        '-i', str(test_dir / 'input'),
        '-o', str(output_dir),
        '-f', str(failed_dir),
        '-l', str(log_dir),
        '-c', str(config_file),
        '-w', '2'  # Use only 2 workers for test
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=False, text=True)
        print("\n" + "=" * 70)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 70)

        # Check output
        output_file = output_dir / 'mindoverclutter_ca_cleaned.jsonl'
        if output_file.exists():
            with open(output_file, 'r') as f:
                lines = f.readlines()
            print(f"\n✓ Output file created: {output_file}")
            print(f"  Cleaned records: {len(lines)}")

            if lines:
                print(f"\n  Sample output (first record):")
                sample = json.loads(lines[0])
                print(f"    ID: {sample['id']}")
                print(f"    Title: {sample['meta']['data_info']['title']}")
                print(f"    Domain: {sample['meta']['content_info']['domain']}")
                print(f"    Subdomain: {sample['meta']['content_info']['subdomain']}")
                print(f"    Text length: {len(sample['text'])} chars")

        print(f"\n  Review files in: {test_dir}")
        print(f"  To clean up: rm -rf {test_dir}")

    except subprocess.CalledProcessError as e:
        print(f"\n✗ TEST FAILED")
        print(f"  Error: {e}")
        print(f"\n  Check logs in: {log_dir}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(run_test())