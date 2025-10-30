#!/usr/bin/env python3

"""
Splits a large text file into smaller parts based on a specified line count.
"""

import argparse
import sys
import os


def split_file(input_file, split_count, prefix, output_dir, start_index):
    """
    Core logic to split the file.
    """

    # Ensure the output directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Could not create directory {output_dir}. {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_file, 'r', encoding='utf-8') as f_in:
            line_count = 0
            file_index = start_index
            output_file = None
            files_created_count = 0

            for line in f_in:
                # If we are at the start of a new chunk, open a new file
                if line_count == 0:
                    # Close the previous file if it's open
                    if output_file:
                        output_file.close()

                    # Create new file path
                    output_filename = f"{prefix}_{file_index}.txt"
                    output_filepath = os.path.join(output_dir, output_filename)

                    print(f"Creating file: {output_filepath}", file=sys.stderr)
                    output_file = open(output_filepath, 'w', encoding='utf-8')
                    file_index += 1
                    files_created_count += 1

                # Write the line to the current output file
                output_file.write(line)
                line_count += 1

                # If we've reached the split count, reset counter
                if line_count >= split_count:
                    line_count = 0

            # Close the last file after the loop finishes
            if output_file:
                output_file.close()

            if files_created_count == 0 and line_count == 0:
                print("Input file was empty. No files created.", file=sys.stderr)
            else:
                print(f"\nDone. Successfully split into {files_created_count} file(s).", file=sys.stderr)

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """
    Main function to parse arguments and call the split function.
    """
    parser = argparse.ArgumentParser(
        description="Split a text file into smaller parts.",
        epilog="""Example:
  python split_list.py -i new_target.txt --split 50 --prefix target --dir ./output

This will create files like ./output/target_1.txt, ./output/target_2.txt, etc.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Input file to split (one item per line)."
    )

    parser.add_argument(
        "--split",
        type=int,
        default=50,
        help="Number of lines per split file. (Default: 50)"
    )

    parser.add_argument(
        "--prefix",
        default="part",
        help="Prefix for output files (e.g., 'target' -> target_1.txt). (Default: 'part')"
    )

    parser.add_argument(
        "--dir",
        default=".",
        help="Output directory to save split files. (Default: current directory)"
    )

    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="The number to start counting file indexes from. (Default: 1)"
    )

    args = parser.parse_args()

    if args.split <= 0:
        print("Error: --split value must be greater than 0.", file=sys.stderr)
        sys.exit(1)

    split_file(args.input, args.split, args.prefix, args.dir, args.start_index)

if __name__ == "__main__":
    main()