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
    """Parse XML configuration file and return header-library pairs, namespace, include directories, and renames"""
    try:
        tree = ET.parse(config_path)
        root = tree.getroot()
        
        if root.tag != 'bindings':
            raise ValueError(f"Expected root element 'bindings', got '{root.tag}'")
        
        header_library_pairs = []
        namespace = None  # Keep for backwards compatibility, but will be deprecated
        include_dirs = []
        renames = []  # Changed to list of (from, to, is_regex) tuples
        removals = []  # List of (pattern, is_regex) tuples
        library_class_names = {}  # Map library name to class name
        library_namespaces = {}  # Map library name to namespace
        library_using_statements = {}  # Map library name to list of using statements
        
        # Get global include directories
        for include_dir in root.findall('include_directory'):
            path = include_dir.get('path')
            if not path:
                raise ValueError("Include directory element missing 'path' attribute")
            include_dirs.append(path.strip())
        
        # Get global renames (support both simple and regex)
        for rename in root.findall('rename'):
            from_name = rename.get('from')
            to_name = rename.get('to')
            if not from_name or not to_name:
                raise ValueError("Rename element missing 'from' or 'to' attribute")
            is_regex = rename.get('regex', 'false').lower() == 'true'
            renames.append((from_name.strip(), to_name.strip(), is_regex))
        
        # Get global removals (support both simple and regex)
        for remove in root.findall('remove'):
            pattern = remove.get('pattern')
            if not pattern:
                raise ValueError("Remove element missing 'pattern' attribute")
            is_regex = remove.get('regex', 'false').lower() == 'true'
            removals.append((pattern.strip(), is_regex))
        
        for library in root.findall('library'):
            library_name = library.get('name')
            if not library_name:
                raise ValueError("Library element missing 'name' attribute")
            
            # Get class name (default to NativeMethods if not specified)
            class_name = library.get('class', 'NativeMethods')
            library_class_names[library_name.strip()] = class_name.strip()
            
            # Get namespace from library attribute
            library_namespace = library.get('namespace')
            if library_namespace is not None:
                library_namespaces[library_name.strip()] = library_namespace.strip()
                # For single-file generation, use first namespace found
                if namespace is None:
                    namespace = library_namespace.strip()
            
            # Get using statements
            using_statements = []
            for using in library.findall('using'):
                using_namespace = using.get('namespace')
                if using_namespace:
                    using_statements.append(using_namespace.strip())
            if using_statements:
                library_using_statements[library_name.strip()] = using_statements
            
            # Get library-specific include directories
            for include_dir in library.findall('include_directory'):
                path = include_dir.get('path')
                if not path:
                    raise ValueError(f"Include directory element in library '{library_name}' missing 'path' attribute")
                include_dirs.append(path.strip())
            
            # Get include files
            for include in library.findall('include'):
                header_path = include.get('file')
                if not header_path:
                    raise ValueError(f"Include element in library '{library_name}' missing 'file' attribute")
                header_library_pairs.append((header_path.strip(), library_name.strip()))
        
        return header_library_pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements
        
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
  %(prog)s --config bindings.xml --output output_dir -I /usr/include
  %(prog)s -C config.xml -o generated_bindings --include-depth 2
        """
    )
    
    parser.add_argument(
        "-C", "--config",
        metavar="CONFIG_FILE",
        required=True,
        help="XML configuration file specifying bindings to generate"
    )
    
    parser.add_argument(
        "-o", "--output",
        metavar="DIRECTORY",
        required=True,
        help="Output directory for generated C# files"
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
    
    args = parser.parse_args()

    # Handle configuration file (now required)
    header_library_pairs = []
    config_namespace = None
    config_include_dirs = []
    config_renames = {}
    
    try:
        header_library_pairs, config_namespace, config_include_dirs, config_renames, config_removals, config_library_class_names, config_library_namespaces, config_library_using_statements = parse_config_file(args.config)
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
            library_using_statements=config_library_using_statements
        )
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
