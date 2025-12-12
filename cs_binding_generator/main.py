#!/usr/bin/env python3
"""
CLI entry point for C# bindings generator
Generates modern C# code with LibraryImport for P/Invoke
"""

import argparse
import sys
import os
import xml.etree.ElementTree as ET
from pathlib import Path
import clang.cindex

# Add parent directory to sys.path for direct execution
if __name__ == '__main__' and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cs_binding_generator.generator import CSharpBindingsGenerator


def parse_config_file(config_path):
    """Parse XML configuration file and return header-library pairs and namespace"""
    try:
        tree = ET.parse(config_path)
        root = tree.getroot()
        
        if root.tag != 'bindings':
            raise ValueError(f"Expected root element 'bindings', got '{root.tag}'")
        
        header_library_pairs = []
        namespace = None
        
        for library in root.findall('library'):
            library_name = library.get('name')
            if not library_name:
                raise ValueError("Library element missing 'name' attribute")
            
            # Get namespace (use first one found as default)
            namespace_elem = library.find('namespace')
            if namespace_elem is not None and namespace is None:
                namespace = namespace_elem.get('name')
            
            # Get include files
            for include in library.findall('include'):
                header_path = include.get('file')
                if not header_path:
                    raise ValueError(f"Include element in library '{library_name}' missing 'file' attribute")
                header_library_pairs.append((header_path.strip(), library_name.strip()))
        
        return header_library_pairs, namespace
        
    except ET.ParseError as e:
        raise ValueError(f"XML parsing error: {e}")
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate C# bindings from C header files using LibraryImport",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i mylib.h:mylib -o MyBindings.cs
  %(prog)s -i header1.h:native -i header2.h:native -o Bindings.cs -n My.Library  
  %(prog)s -i SDL.h:SDL3 -i libtcod.h:libtcod -o Bindings.cs
  %(prog)s -C config.xml -o output_dir --multi -I /usr/include
  %(prog)s --config bindings.xml --include-depth 2 -o MyBindings.cs
        """
    )
    
    parser.add_argument(
        "-C", "--config",
        metavar="CONFIG_FILE",
        help="XML configuration file specifying bindings to generate"
    )
    
    parser.add_argument(
        "-i", "--input",
        action="append",
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

    # Handle configuration file vs direct input
    header_library_pairs = []
    config_namespace = None
    
    if args.config:
        if args.input:
            print("Error: Cannot specify both --config and --input. Use either config file or direct input.", file=sys.stderr)
            sys.exit(1)
            
        try:
            header_library_pairs, config_namespace = parse_config_file(args.config)
        except (ValueError, FileNotFoundError) as e:
            print(f"Error reading config file: {e}", file=sys.stderr)
            sys.exit(1)
            
        if not header_library_pairs:
            print("Error: No libraries found in config file", file=sys.stderr)
            sys.exit(1)
            
    elif args.input:
        # Parse header:library pairs from command line
        for input_spec in args.input:
            if ':' not in input_spec:
                print(f"Error: Input must be in format 'header.h:library'. Got: {input_spec}", file=sys.stderr)
                sys.exit(1)
            
            header_path, library_name = input_spec.split(':', 1)
            header_library_pairs.append((header_path.strip(), library_name.strip()))
    else:
        print("Error: Must specify either --config or --input", file=sys.stderr)
        sys.exit(1)
    
    # Use namespace from config file if available, otherwise use command line argument
    namespace = config_namespace if config_namespace else args.namespace

    # Set clang library path if provided
    if args.clang_path:
        clang.cindex.Config.set_library_path(args.clang_path)

    # Generate bindings
    try:
        generator = CSharpBindingsGenerator()
        generator.generate(
            header_library_pairs,
            output=args.output, 
            namespace=namespace,
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
