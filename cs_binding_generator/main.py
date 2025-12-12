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
if __name__ == '__main__' and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cs_binding_generator.generator import CSharpBindingsGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Generate C# bindings from C header files using LibraryImport",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i mylib.h:mylib -o MyBindings.cs
  %(prog)s -i header1.h:native -i header2.h:native -o Bindings.cs -n My.Library  
  %(prog)s -i SDL.h:SDL3 -i libtcod.h:libtcod -o Bindings.cs
  %(prog)s -i mylib.h:mylib -I /usr/include --include-depth 1 -o Bindings.cs
        """
    )
    
    parser.add_argument(
        "-i", "--input",
        action="append",
        required=True,
        metavar="HEADER:LIBRARY",
        help="Input C header file(s) to process as 'header.h:libname' pairs (can be specified multiple times)"
    )
    
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Output C# file (if not specified, prints to stdout)"
    )

    parser.add_argument(
        "-n", "--namespace",
        default="Bindings",
        metavar="NAMESPACE",
        help="C# namespace for generated code (default: Bindings)"
    )
    
    parser.add_argument(
        "-I", "--include",
        action="append",
        dest="include_dirs",
        metavar="DIR",
        help="Add directory to include search path (can be specified multiple times)"
    )
    
    parser.add_argument(
        "--include-depth",
        type=int,
        default=None,
        metavar="N",
        help="Process included files up to depth N (0=only input files, 1=direct includes, etc.; default: infinite)"
    )
    
    parser.add_argument(
        "--clang-path",
        metavar="PATH",
        help="Path to libclang library (if not in default location)"
    )
    
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Continue processing even if some header files are not found (default: fail on missing files)"
    )
    
    parser.add_argument(
        "--multi",
        action="store_true",
        help="Generate separate files per library in output directory (changes -o to directory path)"
    )
    
    args = parser.parse_args()

    # Parse header:library pairs
    header_library_pairs = []
    for input_spec in args.input:
        if ':' not in input_spec:
            print(f"Error: Input must be in format 'header.h:library'. Got: {input_spec}", file=sys.stderr)
            sys.exit(1)
        
        header_path, library_name = input_spec.split(':', 1)
        header_library_pairs.append((header_path.strip(), library_name.strip()))

    # Set clang library path if provided
    if args.clang_path:
        clang.cindex.Config.set_library_path(args.clang_path)

    # Generate bindings
    try:
        generator = CSharpBindingsGenerator()
        generator.generate(
            header_library_pairs,
            output=args.output, 
            namespace=args.namespace,
            include_dirs=args.include_dirs or [],
            include_depth=args.include_depth,
            ignore_missing=args.ignore_missing,
            multi_file=args.multi
        )
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
