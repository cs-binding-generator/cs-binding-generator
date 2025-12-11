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
  %(prog)s -i mylib.h -o MyBindings.cs -l mylib
  %(prog)s -i header1.h header2.h -o Bindings.cs -l native -n My.Library
  %(prog)s -i mylib.h -I /usr/include -I ./include -o Bindings.cs -l mylib
  %(prog)s -i mylib.h --include-depth 1 -o Bindings.cs -l mylib
        """
    )
    
    parser.add_argument(
        "-i", "--input",
        action="append",
        required=True,
        metavar="HEADER",
        help="Input C header file(s) to process (can be specified multiple times)"
    )
    
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Output C# file (if not specified, prints to stdout)"
    )
    
    parser.add_argument(
        "-l", "--library",
        required=True,
        metavar="NAME",
        help="Name of the native library (e.g., 'mylib' for mylib.dll/libmylib.so)"
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
    
    args = parser.parse_args()
    
    # Set clang library path if provided
    if args.clang_path:
        clang.cindex.Config.set_library_path(args.clang_path)
    
    # Generate bindings
    try:
        generator = CSharpBindingsGenerator(args.library)
        generator.generate(
            args.input, 
            args.output, 
            args.namespace,
            include_dirs=args.include_dirs or [],
            include_depth=args.include_depth
        )
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
