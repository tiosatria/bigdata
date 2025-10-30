#!/usr/bin/env python3

"""
A script to deduplicate a list of URLs against itself and/or another list.
"""

import argparse
import sys


def load_urls_from_file(filepath):
    """
    Loads URLs from a file, stripping whitespace and skipping empty lines.
    Returns a list of URLs.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # Read all lines, strip whitespace from ends
            urls = [line.strip() for line in f]
            # Filter out any empty strings that result from empty lines
            return [url for url in urls if url]
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        sys.exit(1)


def get_ordered_unique(urls):
    """
    Returns a new list containing unique URLs from the input list,
    preserving the original order of the first appearance of each URL.
    """
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


def main():
    """
    Main function to parse arguments and perform deduplication.
    """
    parser = argparse.ArgumentParser(
        description="Deduplicate a list of URLs against itself or another list.",
        epilog="""Examples:
  1. Dedupe against itself and save to a new file:
     python dedupe_url_list.py -i input.txt -o output.txt

  2. Dedupe against another file and print to screen:
     python dedupe_url_list.py -i input.txt --against input2.txt

  3. Dedupe against another file and save to a new file:
     python dedupe_url_list.py -i input.txt --against input2.txt -o output.txt
     """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Input file containing URLs (one per line)."
    )
    parser.add_argument(
        "-o", "--output",
        help="Optional output file to write unique URLs. (Default: prints to screen/stdout)."
    )
    parser.add_argument(
        "--against",
        dest="against_file",
        help="Optional file of URLs to deduplicate against."
    )

    args = parser.parse_args()

    # 1. Load and self-dedupe the primary input list
    # This fulfills the "dedupe against itself" requirement.
    input_urls = load_urls_from_file(args.input)
    unique_input_urls = get_ordered_unique(input_urls)

    final_output_list = []

    # 2. Check if we are deduping against another file
    if args.against_file:
        print(f"Filtering against URLs in {args.against_file}...", file=sys.stderr)
        # Load the "against" URLs into a set for fast lookup
        against_urls = load_urls_from_file(args.against_file)
        against_set = set(against_urls)

        # Filter the main list: keep URLs that are NOT in the "against" set
        final_output_list = [url for url in unique_input_urls if url not in against_set]
    else:
        # No "against" file, so the output is just the self-deduped list
        print("Performing self-deduplication...", file=sys.stderr)
        final_output_list = unique_input_urls

    # 3. Handle the output
    # Join all URLs in the final list with a newline
    output_string = "\n".join(final_output_list)

    if args.output:
        # Write to the specified output file
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_string)
                # Add a final newline if the list wasn't empty
                if output_string:
                    f.write("\n")
            print(f"Wrote {len(final_output_list)} URLs to {args.output}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing to {args.output}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # No output file specified, print to stdout
        if output_string:
            print(output_string)
        print(f"Printed {len(final_output_list)} URLs to stdout.", file=sys.stderr)


if __name__ == "__main__":
    main()