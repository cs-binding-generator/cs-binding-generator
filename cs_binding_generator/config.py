"""
XML configuration file parsing for C# bindings generator
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class BindingConfig:
    """Configuration for C# bindings generation"""
    header_library_pairs: list[tuple[str, str]] = field(default_factory=list)
    include_dirs: list[str] = field(default_factory=list)
    renames: list[tuple[str, str, bool]] = field(default_factory=list)
    removals: list[tuple[str, bool]] = field(default_factory=list)
    flag_enums: list[tuple[str, bool]] = field(default_factory=list)
    library_class_names: dict[str, str] = field(default_factory=dict)
    library_namespaces: dict[str, str] = field(default_factory=dict)
    library_using_statements: dict[str, list[str]] = field(default_factory=dict)
    visibility: str = "public"
    global_constants: list[tuple[str, str, str, bool]] = field(default_factory=list)
    global_defines: list[tuple[str, str | None]] = field(default_factory=list)
    utf8_byte_overloads: bool = False
    # Per-(struct, field) type overrides — keyed by the C struct and field name (pre-rename).
    # Lets the user point a raw `uint`/`byte` field at a flag-enum type so call sites can
    # write `usage = MyFlags.X | MyFlags.Y` instead of `(uint)(MyFlags.X | MyFlags.Y)`.
    typed_fields: dict[tuple[str, str], str] = field(default_factory=dict)
    # Same idea for function parameters: (function, param) -> type name.
    typed_params: dict[tuple[str, str], str] = field(default_factory=dict)


def parse_config_file(config_path):
    """Parse XML configuration file and return BindingConfig object"""
    try:
        tree = ET.parse(config_path)
        root = tree.getroot()

        if root.tag != "bindings":
            raise ValueError(f"Expected root element 'bindings', got '{root.tag}'")

        config = BindingConfig()

        # Get global visibility setting (default to "public")
        config.visibility = root.get("visibility", "public").strip().lower()
        if config.visibility not in ("public", "internal"):
            import sys
            print(f"Error: Invalid visibility value '{config.visibility}'. Must be 'public' or 'internal'.", file=sys.stderr)
            sys.exit(1)

        # Get global include directories
        for include_dir in root.findall("include_directory"):
            path = include_dir.get("path")
            if not path:
                raise ValueError("Include directory element missing 'path' attribute")
            config.include_dirs.append(path.strip())

        # Get global renames (support both simple and regex)
        for rename in root.findall("rename"):
            from_name = rename.get("from")
            to_name = rename.get("to")
            if not from_name or not to_name:
                raise ValueError("Rename element missing 'from' or 'to' attribute")
            is_regex = rename.get("regex", "false").lower() == "true"
            config.renames.append((from_name.strip(), to_name.strip(), is_regex))

        # Get global removals (support both simple and regex)
        for remove in root.findall("remove"):
            pattern = remove.get("pattern")
            if not pattern:
                raise ValueError("Remove element missing 'pattern' attribute")
            is_regex = remove.get("regex", "false").lower() == "true"
            config.removals.append((pattern.strip(), is_regex))

        # Get global flag enums (enum patterns that should have [Flags] attribute)
        for flag_enum in root.findall("flags"):
            pattern = flag_enum.get("pattern")
            if not pattern:
                raise ValueError("Flags element missing 'pattern' attribute")
            is_regex = flag_enum.get("regex", "false").lower() == "true"
            config.flag_enums.append((pattern.strip(), is_regex))

        # Get global compiler defines
        for define in root.findall("define"):
            name = define.get("name")
            if not name:
                raise ValueError("Define element missing 'name' attribute")
            value = define.get("value")  # Optional, can be None
            if value is not None:
                value = value.strip()
            config.global_defines.append((name.strip(), value))

        # Get global constants (macros to extract)
        # These are stored as a list of (name, pattern, type, is_flags) tuples
        # They will be applied to all libraries during processing.
        # The `name` attribute is required for numeric constants groups (which become a
        # named C# enum) but optional for `type="string"` groups (which emit each macro
        # as a member of the library's static class with no wrapper type).
        for const in root.findall("constants"):
            const_name = const.get("name")
            const_pattern = const.get("pattern")
            const_type = const.get("type", "uint").strip()
            const_flags = const.get("flags", "false").lower() == "true"

            if not const_pattern:
                raise ValueError("Constants element missing 'pattern' attribute")
            if const_type != "string" and not const_name:
                raise ValueError("Constants element missing 'name' attribute")

            config.global_constants.append(
                ((const_name or "").strip(), const_pattern.strip(), const_type, const_flags)
            )

        # Opt-in: for every function that has at least one `string?` parameter (mapped
        # from a C char* arg), emit a parallel byte*-param overload alongside the primary
        # P/Invoke. Lets callers pass pre-encoded UTF-8 buffers (u8 literals, pinned spans)
        # without the round trip through Encoding.UTF8 → marshaller → native.
        if root.find("utf8-byte-overloads") is not None:
            config.utf8_byte_overloads = True

        # Per-(struct, field) type overrides. Each entry replaces the auto-mapped C# type
        # on a single struct field with whatever the user specifies (typically a [Flags]
        # enum extracted via <constants>). The struct/field names use the C identifier,
        # before any rename rule fires.
        for tf in root.findall("typed-field"):
            struct_name = tf.get("struct")
            field_name = tf.get("field")
            type_name = tf.get("type")
            if not struct_name or not field_name or not type_name:
                raise ValueError(
                    "typed-field element missing one of 'struct', 'field', 'type' attributes"
                )
            config.typed_fields[(struct_name.strip(), field_name.strip())] = type_name.strip()

        # Per-(function, param) type overrides. Same mechanism, applied to function
        # parameters. The function/param names use the C identifier, before renames.
        for tp in root.findall("typed-param"):
            func_name = tp.get("function")
            param_name = tp.get("param")
            type_name = tp.get("type")
            if not func_name or not param_name or not type_name:
                raise ValueError(
                    "typed-param element missing one of 'function', 'param', 'type' attributes"
                )
            config.typed_params[(func_name.strip(), param_name.strip())] = type_name.strip()

        for library in root.findall("library"):
            library_name = library.get("name")
            if not library_name:
                raise ValueError("Library element missing 'name' attribute")

            # Get class name (default to NativeMethods if not specified)
            class_name = library.get("class", "NativeMethods")
            config.library_class_names[library_name.strip()] = class_name.strip()

            # Get namespace from library attribute
            library_namespace = library.get("namespace")
            if library_namespace is not None:
                config.library_namespaces[library_name.strip()] = library_namespace.strip()

            # Get using statements
            using_statements = []
            for using in library.findall("using"):
                using_namespace = using.get("namespace")
                if using_namespace:
                    using_statements.append(using_namespace.strip())
            if using_statements:
                config.library_using_statements[library_name.strip()] = using_statements

            # Get library-specific include directories
            for include_dir in library.findall("include_directory"):
                path = include_dir.get("path")
                if not path:
                    raise ValueError(f"Include directory element in library '{library_name}' missing 'path' attribute")
                config.include_dirs.append(path.strip())

            # Get include files
            for include in library.findall("include"):
                header_path = include.get("file")
                if not header_path:
                    raise ValueError(f"Include element in library '{library_name}' missing 'file' attribute")
                config.header_library_pairs.append((header_path.strip(), library_name.strip()))

        return config

    except ET.ParseError as e:
        raise ValueError(f"XML parsing error: {e}")
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
