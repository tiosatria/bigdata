'''import argparse
import os
from urllib.parse import urlparse

def generate_config_file(domain, seeds, nav_hints, article_hints, parser_type, force=False):
    """Generates a domain configuration file."""

    # Sanitize domain to create a valid filename
    filename_domain = domain.replace('.', '_')
    config_dir = os.path.join(os.path.dirname(__file__), 'bigdata', 'domain_configs')
    filepath = os.path.join(config_dir, f"{filename_domain}.py")

    if os.path.exists(filepath) and not force:
        print(f"Error: Configuration file already exists at {filepath}")
        print("Use --force to overwrite.")
        return

    # Prepare the content for the configuration file
    content = f"""from bigdata.domain_configs.domain_config import DomainConfig, ParserType

# Configuration for {domain}
{filename_domain.upper()}_CONFIG = DomainConfig(
    domain="{domain}",
    parser_type=ParserType.{parser_type.upper()},
"""

    if seeds:
        seed_list = [f'"{seed}"' for seed in seeds]
        content += f"    seeds=[{', '.join(seed_list)}],
"
    else:
        # Add a default seed if none are provided
        content += f'    seeds=["http://www.{domain}"],
'

    if nav_hints:
        nav_hint_list = [f'"{hint}"' for hint in nav_hints]
        content += f"    navigation_path_hints=[{', '.join(nav_hint_list)}],
"

    if article_hints:
        article_hint_list = [f'"{hint}"' for hint in article_hints]
        content += f"    article_path_hints=[{', '.join(article_hint_list)}],
"

    content += ")
"

    # Write the content to the file
    try:
        os.makedirs(config_dir, exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Successfully generated configuration for {domain} at {filepath}")
    except Exception as e:
        print(f"Error writing configuration file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a new domain configuration for the article spider.")
    
    parser.add_argument("domain", help="The domain to configure (e.g., example.com)")
    parser.add_argument("--seeds", help="Comma-separated list of seed URLs", type=str)
    parser.add_argument("--nav-hints", help="Comma-separated list of navigation path hints (e.g., 'news,blog')", type=str)
    parser.add_argument("--article-hints", help="Comma-separated list of article path hints (e.g., '/article/,/post/')", type=str)
    parser.add_argument("--parser-type", help="The parser type to use (smart or xpath)", default="smart", choices=["smart", "xpath"])
    parser.add_argument("--force", help="Overwrite existing configuration file", action="store_true")

    args = parser.parse_args()

    seeds = args.seeds.split(',') if args.seeds else []
    nav_hints = args.nav_hints.split(',') if args.nav_hints else []
    article_hints = args.article_hints.split(',') if args.article_hints else []

    generate_config_file(args.domain, seeds, nav_hints, article_hints, args.parser_type, args.force)
''