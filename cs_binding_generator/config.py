"""
XML configuration file parsing for C# bindings generator
"""

import xml.etree.ElementTree as ET


def parse_config_file(config_path):
    """Parse XML configuration file and return header-library pairs, include directories, and renames"""
    try:
        tree = ET.parse(config_path)
        root = tree.getroot()

        if root.tag != "bindings":
            raise ValueError(f"Expected root element 'bindings', got '{root.tag}'")

        header_library_pairs = []
        include_dirs = []
        renames = []  # Changed to list of (from, to, is_regex) tuples
        removals = []  # List of (pattern, is_regex) tuples
        library_class_names = {}  # Map library name to class name
        library_namespaces = {}  # Map library name to namespace
        library_using_statements = {}  # Map library name to list of using statements
        library_constants = {}  # Map library name to list of (name, pattern, type) tuples

        # Get global visibility setting (default to "public")
        visibility = root.get("visibility", "public").strip().lower()
        if visibility not in ("public", "internal"):
            import sys
            print(f"Error: Invalid visibility value '{visibility}'. Must be 'public' or 'internal'.", file=sys.stderr)
            sys.exit(1)

        # Get global include directories
        for include_dir in root.findall("include_directory"):
            path = include_dir.get("path")
            if not path:
                raise ValueError("Include directory element missing 'path' attribute")
            include_dirs.append(path.strip())

        # Get global renames (support both simple and regex)
        for rename in root.findall("rename"):
            from_name = rename.get("from")
            to_name = rename.get("to")
            if not from_name or not to_name:
                raise ValueError("Rename element missing 'from' or 'to' attribute")
            is_regex = rename.get("regex", "false").lower() == "true"
            renames.append((from_name.strip(), to_name.strip(), is_regex))

        # Get global removals (support both simple and regex)
        for remove in root.findall("remove"):
            pattern = remove.get("pattern")
            if not pattern:
                raise ValueError("Remove element missing 'pattern' attribute")
            is_regex = remove.get("regex", "false").lower() == "true"
            removals.append((pattern.strip(), is_regex))

        # Get global constants (macros to extract)
        # These are stored as a list of (name, pattern, type) tuples
        # They will be applied to all libraries during processing
        global_constants = []
        for const in root.findall("constants"):
            const_name = const.get("name")
            const_pattern = const.get("pattern")
            const_type = const.get("type", "uint")  # Default to uint

            if not const_name:
                raise ValueError("Constants element missing 'name' attribute")
            if not const_pattern:
                raise ValueError("Constants element missing 'pattern' attribute")

            global_constants.append((const_name.strip(), const_pattern.strip(), const_type.strip()))

        for library in root.findall("library"):
            library_name = library.get("name")
            if not library_name:
                raise ValueError("Library element missing 'name' attribute")

            # Get class name (default to NativeMethods if not specified)
            class_name = library.get("class", "NativeMethods")
            library_class_names[library_name.strip()] = class_name.strip()

            # Get namespace from library attribute
            library_namespace = library.get("namespace")
            if library_namespace is not None:
                library_namespaces[library_name.strip()] = library_namespace.strip()

            # Get using statements
            using_statements = []
            for using in library.findall("using"):
                using_namespace = using.get("namespace")
                if using_namespace:
                    using_statements.append(using_namespace.strip())
            if using_statements:
                library_using_statements[library_name.strip()] = using_statements

            # Get library-specific include directories
            for include_dir in library.findall("include_directory"):
                path = include_dir.get("path")
                if not path:
                    raise ValueError(f"Include directory element in library '{library_name}' missing 'path' attribute")
                include_dirs.append(path.strip())

            # Get include files
            for include in library.findall("include"):
                header_path = include.get("file")
                if not header_path:
                    raise ValueError(f"Include element in library '{library_name}' missing 'file' attribute")
                header_library_pairs.append((header_path.strip(), library_name.strip()))

        return (
            header_library_pairs,
            include_dirs,
            renames,
            removals,
            library_class_names,
            library_namespaces,
            library_using_statements,
            visibility,
            global_constants,
        )

    except ET.ParseError as e:
        raise ValueError(f"XML parsing error: {e}")
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
