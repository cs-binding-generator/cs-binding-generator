#!/usr/bin/env python3
"""
CLI entry point for C# bindings generator
Generates modern C# code with LibraryImport for P/Invoke
"""

import argparse
import sys
import os
import clang.cindex

# Add parent directory to sys.path for direct execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cs_binding_generator.generator import CSharpBindingsGenerator
from cs_binding_generator.config import parse_config_file


def main():
    parser = argparse.ArgumentParser(
        description="Generate C# bindings from C header files using LibraryImport",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --config bindings.xml --output output_dir -I /usr/include
  %(prog)s -C config.xml -o generated_bindings --include-depth 2
        """,
    )

    parser.add_argument(
        "-C",
        "--config",
        metavar="CONFIG_FILE",
        required=True,
        help="XML configuration file specifying bindings to generate",
    )

    parser.add_argument(
        "-o", "--output", metavar="DIRECTORY", required=True, help="Output directory for generated C# files"
    )

    parser.add_argument(
        "--include-depth",
        type=int,
        default=None,
        metavar="N",
        help="Process included files up to depth N (0=only input files, 1=direct includes, etc.; default: infinite)",
    )

    parser.add_argument("--clang-path", metavar="PATH", help="Path to libclang library (if not in default location)")

    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Continue processing even if some header files are not found (default: fail on missing files)",
    )

    args = parser.parse_args()

    # Handle configuration file (now required)
    header_library_pairs = []
    config_include_dirs = []
    config_renames = {}

    try:
        (
            header_library_pairs,
            config_include_dirs,
            config_renames,
            config_removals,
            config_library_class_names,
            config_library_namespaces,
            config_library_using_statements,
        ) = parse_config_file(args.config)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)

    if not header_library_pairs:
        print("Error: No libraries found in config file", file=sys.stderr)
        sys.exit(1)

    # Include directories are now defined in the config file
    include_dirs = config_include_dirs

    # Set clang library path if provided
    if args.clang_path:
        clang.cindex.Config.set_library_path(args.clang_path)

    # Generate bindings
    try:
        generator = CSharpBindingsGenerator()

        # Apply renames if using config file
        if args.config and config_renames:
            for from_name, to_name, is_regex in config_renames:
                generator.type_mapper.add_rename(from_name, to_name, is_regex)

        # Apply removals if using config file
        if args.config and config_removals:
            for pattern, is_regex in config_removals:
                generator.type_mapper.add_removal(pattern, is_regex)

        generator.generate(
            header_library_pairs,
            output=args.output,
            include_dirs=include_dirs,
            include_depth=args.include_depth,
            ignore_missing=args.ignore_missing,
            library_class_names=config_library_class_names,
            library_namespaces=config_library_namespaces,
            library_using_statements=config_library_using_statements,
        )
    except Exception as e:
        import traceback

        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
