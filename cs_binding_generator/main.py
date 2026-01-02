#!/usr/bin/env python3
"""
CLI entry point for C# bindings generator
Generates modern C# code with LibraryImport for P/Invoke
"""

import argparse
import os
import sys

import clang.cindex

# Add parent directory to sys.path for direct execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cs_binding_generator.config import parse_config_file
from cs_binding_generator.generator import CSharpBindingsGenerator
from cs_binding_generator import __version__


def main():
    parser = argparse.ArgumentParser(
        description=f"C# Bindings Generator v{__version__}\nGenerate C# bindings from C header files using LibraryImport",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --config bindings.xml --output output_dir
  %(prog)s -C config.xml -o generated_bindings
  %(prog)s  # Uses default cs-bindings.xml in current directory
        """,
    )

    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version number and exit"
    )

    parser.add_argument(
        "-C",
        "--config",
        metavar="CONFIG_FILE",
        help="XML configuration file specifying bindings to generate (default: cs-bindings.xml in current directory)",
    )

    parser.add_argument(
        "-o", "--output", metavar="DIRECTORY", help="Output directory for generated C# files (default: current directory)"
    )

    parser.add_argument("--clang-path", metavar="PATH", help="Path to libclang library (if not in default location)")

    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Continue processing even if some header files are not found (default: fail on missing files)",
    )

    parser.add_argument(
        "--use-variadic",
        action="store_true",
        help="Generate variadic functions with __arglist parameter using DllImport (non-AOT compatible). By default, variadic functions are generated with the variadic parameter omitted, which typically works due to calling conventions but may cause stack cleanup issues.",
    )

    args = parser.parse_args()

    # Default config file to cs-bindings.xml in current directory if not specified
    if not args.config:
        default_config = "cs-bindings.xml"
        if os.path.exists(default_config):
            args.config = default_config
            print(f"Using default config file: {default_config}")
        else:
            print(f"Error: No config file specified and default '{default_config}' not found in current directory", file=sys.stderr)
            print("Please provide a config file with --config or create cs-bindings.xml in the current directory", file=sys.stderr)
            sys.exit(1)

    # Default output to current directory if not specified
    if not args.output:
        args.output = "."

    # Handle configuration file
    try:
        config = parse_config_file(args.config)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)

    if not config.header_library_pairs:
        print("Error: No libraries found in config file", file=sys.stderr)
        sys.exit(1)

    # Set clang library path if provided
    if args.clang_path:
        clang.cindex.Config.set_library_path(args.clang_path)

    # Generate bindings
    try:
        generator = CSharpBindingsGenerator()

        # Apply renames if using config file
        if args.config and config.renames:
            for from_name, to_name, is_regex in config.renames:
                generator.type_mapper.add_rename(from_name, to_name, is_regex)

        # Apply removals if using config file
        if args.config and config.removals:
            for pattern, is_regex in config.removals:
                generator.type_mapper.add_removal(pattern, is_regex)

        # Apply flag enum patterns if using config file
        if args.config and config.flag_enums:
            for pattern, is_regex in config.flag_enums:
                generator.type_mapper.add_flag_enum(pattern, is_regex)

        generator.generate(
            config.header_library_pairs,
            output=args.output,
            include_dirs=config.include_dirs,
            ignore_missing=args.ignore_missing,
            skip_variadic=not args.use_variadic,
            library_class_names=config.library_class_names,
            library_namespaces=config.library_namespaces,
            library_using_statements=config.library_using_statements,
            visibility=config.visibility,
            global_constants=config.global_constants,
            global_defines=config.global_defines,
        )
    except Exception as e:
        import traceback

        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
