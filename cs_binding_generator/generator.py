"""
Main C# bindings generator orchestration
"""

import re
import sys
from pathlib import Path
from typing import Optional

import clang.cindex
from clang.cindex import CursorKind

from .code_generators import CodeGenerator, OutputBuilder
from .constants import DEFAULT_NAMESPACE, NATIVE_METHODS_CLASS
from .type_mapper import TypeMapper


class CSharpBindingsGenerator:
    """Main orchestrator for generating C# bindings from C headers"""

    def __init__(self):
        self.type_mapper = TypeMapper()
        self.code_generator = None  # Will be initialized with visibility setting
        self.visibility = "public"  # Default visibility

        # Store generated items by library
        self.generated_functions = {}  # library -> [functions]
        self.generated_structs = {}  # library -> [structs]
        self.generated_unions = {}  # library -> [unions]
        self.generated_enums = {}  # library -> [enums]
        self.source_file = None
        self.allowed_files = set()  # Files allowed based on include depth

        # Track what we've already generated to avoid duplicates
        self.seen_functions = set()  # (name, location)
        self.seen_structs = set()  # (name, location)
        self.seen_unions = set()  # (name, location)
        self.enum_members = {}  # name -> (library, list of (member_name, value) tuples, underlying_type)

        # Store captured macros by library: library -> {macro_name: value}
        self.captured_macros = {}  # library -> {macro_name: value}

    def _add_to_library_collection(self, collection: dict, library: str, item: str):
        """Add an item to a library-specific collection"""
        if library not in collection:
            collection[library] = []
        collection[library].append(item)

    def _clear_state(self):
        """Clear all accumulated state for a new generation run"""
        self.generated_functions.clear()
        self.generated_structs.clear()
        self.generated_unions.clear()
        self.generated_enums.clear()
        self.seen_functions.clear()
        self.seen_structs.clear()
        self.seen_unions.clear()
        self.enum_members.clear()
        self.captured_macros.clear()
        self.source_file = None
        self.allowed_files.clear()

    def _extract_macros_from_file(self, file_path: str, patterns: list[str]) -> dict[str, str]:
        """Extract #define macros from a header file that match the given patterns

        Args:
            file_path: Path to the header file
            patterns: List of regex patterns to match macro names

        Returns:
            Dict mapping macro names to their values
        """
        macros = {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # Look for #define directives with simple numeric values
                    # Pattern: #define NAME VALUE
                    match = re.match(r'^\s*#\s*define\s+(\w+)\s+(.+?)(?://.*)?$', line)
                    if match:
                        macro_name = match.group(1)
                        macro_value = match.group(2).strip()

                        # Strip C-style comments (/**< ... */ or /* ... */)
                        macro_value = re.sub(r'/\*.*?\*/', '', macro_value).strip()

                        # Strip trailing commas
                        macro_value = macro_value.rstrip(',')

                        # Strip C cast macros like SDL_UINT64_C(0x...) and extract the value
                        cast_match = re.match(r'^\w+\((.*)\)$', macro_value)
                        if cast_match:
                            macro_value = cast_match.group(1).strip()

                        # Only capture macros with numeric-looking values or simple expressions
                        # Skip macros that reference other identifiers (which would need evaluation)
                        if self._is_numeric_macro_value(macro_value):
                            # Check if this macro matches any of the patterns
                            for pattern in patterns:
                                if re.fullmatch(pattern, macro_name):
                                    macros[macro_name] = macro_value
                                    break
        except Exception as e:
            # If we can't read the file, just skip it
            pass

        return macros

    def _is_numeric_macro_value(self, value: str) -> bool:
        """Check if a macro value looks numeric (number, cast, or simple expression)

        Returns True for:
        - Plain numbers: 0x123, 123, -1
        - Cast expressions: SDL_UINT64_C(0x123)
        - Simple arithmetic: (1 << 5)

        Returns False for:
        - Identifier references: SDL_WINDOW_SOMETHING (would need evaluation)
        """
        # If it contains bare uppercase identifiers (not in function calls), skip it
        # This catches things like "SDL_WINDOW_HIGH_PIXEL_DENSITY" which reference other macros
        # Pattern: uppercase identifier that's not immediately followed by (
        if re.match(r'^[A-Z_][A-Z0-9_]+$', value):
            return False

        # Check if it's a plain number (hex, decimal, negative)
        if re.match(r'^-?\d+$', value) or re.match(r'^0x[0-9A-Fa-f]+$', value):
            return True

        # Check if it's a cast/macro call with numeric content: NAME(0x...)
        if re.match(r'^\w+\(.*\)$', value):
            return True

        # Check if it contains simple arithmetic operators with numbers
        if re.match(r'^[\d\sx()|<<>>+\-*/&^~]+$', value):
            return True

        # Default to False for anything else
        return False

    def _is_system_header(self, file_path: str) -> bool:
        """Check if a file path is a system header that should be excluded"""
        path = Path(file_path).resolve()
        path_str = str(path)

        # Standard C library headers to exclude  - check filename first
        c_std_headers = {
            "assert.h",
            "complex.h",
            "ctype.h",
            "errno.h",
            "fenv.h",
            "float.h",
            "inttypes.h",
            "iso646.h",
            "limits.h",
            "locale.h",
            "math.h",
            "setjmp.h",
            "signal.h",
            "stdalign.h",
            "stdarg.h",
            "stdatomic.h",
            "stdbool.h",
            "stddef.h",
            "stdint.h",
            "stdio.h",
            "stdlib.h",
            "stdnoreturn.h",
            "string.h",
            "tgmath.h",
            "threads.h",
            "time.h",
            "uchar.h",
            "wchar.h",
            "wctype.h",
            "alloca.h",
        }

        filename = path.name
        if filename in c_std_headers:
            return True

        # System directories to exclude entirely
        system_paths = [
            "/usr/include/c++",
            "/usr/include/x86_64-linux-gnu",
            "/usr/include/aarch64-linux-gnu",
            "/usr/lib/gcc",
            "/usr/lib/clang",
            "/usr/local/include",
        ]

        if any(path_str.startswith(sys_path) for sys_path in system_paths):
            return True

        # Filter any header directly in /usr/include or in system subdirectories
        if path_str.startswith("/usr/include/"):
            relative = path_str[len("/usr/include/") :]

            # Filter all headers directly in /usr/include (no subdirectory)
            if "/" not in relative:
                return True

            # Also filter known system subdirectories
            first_part = relative.split("/")[0]
            system_subdirs = {
                "sys",
                "bits",
                "gnu",
                "asm",
                "asm-generic",
                "linux",
                "arpa",
                "net",
                "netinet",
                "rpc",
                "scsi",
                "protocols",
            }
            if first_part in system_subdirs:
                return True

        return False

    def process_cursor(self, cursor):
        """Recursively process AST nodes"""
        # Note: We don't filter files here anymore - we need to see all typedefs
        # to build a complete type resolution map. Filtering happens during code generation.

        if cursor.kind == CursorKind.FUNCTION_DECL:
            # Only generate code for non-system headers
            if cursor.location.file:
                file_path = str(cursor.location.file)
                if file_path not in self.allowed_files or self._is_system_header(file_path):
                    # Don't generate code but still recurse
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
            # Check if this function should be removed
            if self.type_mapper.should_remove(cursor.spelling):
                # Skip this function entirely
                for child in cursor.get_children():
                    self.process_cursor(child)
                return
            # Check if we've already generated this function
            # Use global deduplication to avoid duplicate partial methods
            func_key = cursor.spelling  # Global deduplication by function name
            if func_key not in self.seen_functions:
                code = self.code_generator.generate_function(cursor, self.current_library)
                if code:
                    self._add_to_library_collection(self.generated_functions, self.current_library, code)
                    self.seen_functions.add(func_key)

        elif cursor.kind == CursorKind.STRUCT_DECL:
            if cursor.is_definition():
                # Only generate code for non-system headers
                if cursor.location.file:
                    file_path = str(Path(cursor.location.file.name).resolve())
                    if file_path not in self.allowed_files or self._is_system_header(file_path):
                        # Don't generate code but still recurse
                        for child in cursor.get_children():
                            self.process_cursor(child)
                        return
                # Check if this struct should be removed
                if cursor.spelling and self.type_mapper.should_remove(cursor.spelling):
                    # Skip this struct entirely
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
                # Use global deduplication to avoid duplicate struct definitions
                struct_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                if struct_key not in self.seen_structs:
                    code = self.code_generator.generate_struct(cursor)
                    if code:
                        self._add_to_library_collection(self.generated_structs, self.current_library, code)
                        self.seen_structs.add(struct_key)
                        # Also mark as seen by name only to prevent opaque type generation
                        if cursor.spelling:
                            self.seen_structs.add((cursor.spelling, None, None))

        elif cursor.kind == CursorKind.UNION_DECL:
            if cursor.is_definition():
                # Only generate code for non-system headers
                if cursor.location.file:
                    file_path = str(Path(cursor.location.file.name).resolve())
                    if file_path not in self.allowed_files or self._is_system_header(file_path):
                        # Don't generate code but still recurse
                        for child in cursor.get_children():
                            self.process_cursor(child)
                        return
                # Check if this union should be removed
                if cursor.spelling and self.type_mapper.should_remove(cursor.spelling):
                    # Skip this union entirely
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
                # Use global deduplication to avoid duplicate union definitions
                union_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                if union_key not in self.seen_unions:
                    code = self.code_generator.generate_union(cursor)
                    if code:
                        self._add_to_library_collection(self.generated_unions, self.current_library, code)
                        self.seen_unions.add(union_key)

        elif cursor.kind == CursorKind.ENUM_DECL:
            if cursor.is_definition():
                # Only generate code for non-system headers
                if cursor.location.file:
                    file_path = str(Path(cursor.location.file.name).resolve())
                    if file_path not in self.allowed_files or self._is_system_header(file_path):
                        # Don't generate code but still recurse
                        for child in cursor.get_children():
                            self.process_cursor(child)
                        return
                # Check if this enum should be removed
                if cursor.spelling and self.type_mapper.should_remove(cursor.spelling):
                    # Skip this enum entirely
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
                # Collect enum members for merging (handle duplicate enum names)
                self._collect_enum_members(cursor)

        elif cursor.kind == CursorKind.TYPEDEF_DECL:
            # Build typedef resolution map for ALL typedefs (including system headers)
            type_name = cursor.spelling
            underlying_type = cursor.underlying_typedef_type
            if type_name and underlying_type:
                # Store the typedef mapping for later resolution
                self.type_mapper.register_typedef(type_name, underlying_type)

            # Only generate code for non-system opaque struct typedefs
            if cursor.location.file:
                file_path = str(cursor.location.file)
                if file_path not in self.allowed_files or self._is_system_header(file_path):
                    return

            # Handle opaque struct typedefs (e.g., typedef struct SDL_Window SDL_Window;)
            # These are used as handles in C APIs
            children = list(cursor.get_children())
            if len(children) == 1:
                child = children[0]
                # Skip if already generated as a full struct for this library
                if (self.current_library, (type_name, None, None)) in self.seen_structs:
                    return

                # Check if it's a reference to a struct (TYPE_REF) or direct STRUCT_DECL
                if child.kind == CursorKind.TYPE_REF and child.spelling and "struct " in str(child.type.spelling):
                    # This is an opaque typedef like: typedef struct SDL_Window SDL_Window;
                    if type_name and type_name not in [
                        "size_t",
                        "ssize_t",
                        "ptrdiff_t",
                        "intptr_t",
                        "uintptr_t",
                        "wchar_t",
                    ]:
                        struct_key = (type_name, str(cursor.location.file), cursor.location.line)
                        # Use global deduplication
                        if struct_key not in self.seen_structs:
                            code = self.code_generator.generate_opaque_type(type_name)
                            if code:
                                self._add_to_library_collection(self.generated_structs, self.current_library, code)
                                self.seen_structs.add(struct_key)
                                self.seen_structs.add((type_name, None, None))
                                # Register as opaque type for pointer handling
                                self.type_mapper.opaque_types.add(type_name)
                elif child.kind == CursorKind.STRUCT_DECL and not child.is_definition() and child.spelling:
                    # Direct forward declaration
                    struct_key = (child.spelling, str(cursor.location.file), cursor.location.line)
                    # Use global deduplication
                    if struct_key not in self.seen_structs:
                        code = self.code_generator.generate_opaque_type(child.spelling)
                        if code:
                            self._add_to_library_collection(self.generated_structs, self.current_library, code)
                            self.seen_structs.add(struct_key)
                            self.seen_structs.add((child.spelling, None, None))
                            # Register as opaque type for pointer handling
                            self.type_mapper.opaque_types.add(child.spelling)

        # Recurse into children
        for child in cursor.get_children():
            self.process_cursor(child)

    def prescan_opaque_types(self, cursor):
        """Pre-scan AST to identify opaque types before processing functions"""
        # Only process items in allowed files (based on include depth)
        if cursor.location.file:
            file_path = str(cursor.location.file)
            if file_path not in self.allowed_files:
                return

        if cursor.kind == CursorKind.TYPEDEF_DECL:
            # Handle opaque struct typedefs (e.g., typedef struct SDL_Window SDL_Window;)
            children = list(cursor.get_children())
            if len(children) == 1:
                child = children[0]
                type_name = cursor.spelling

                # Check if it's a reference to a struct (TYPE_REF) or direct STRUCT_DECL
                if child.kind == CursorKind.TYPE_REF and child.spelling and "struct " in str(child.type.spelling):
                    # This is an opaque typedef like: typedef struct SDL_Window SDL_Window;
                    if type_name and type_name not in [
                        "size_t",
                        "ssize_t",
                        "ptrdiff_t",
                        "intptr_t",
                        "uintptr_t",
                        "wchar_t",
                    ]:
                        self.type_mapper.opaque_types.add(type_name)
                elif child.kind == CursorKind.STRUCT_DECL and not child.is_definition() and child.spelling:
                    # Direct forward declaration
                    self.type_mapper.opaque_types.add(child.spelling)

        # Recurse into children
        for child in cursor.get_children():
            self.prescan_opaque_types(child)

    def _collect_enum_members(self, cursor):
        """Collect enum members for merging duplicate enums"""
        from clang.cindex import CursorKind

        enum_name = cursor.spelling

        # Filter out invalid enum names (anonymous enums with full display name)
        if enum_name and ("unnamed" in enum_name or "(" in enum_name or "::" in enum_name):
            enum_name = None

        # For anonymous enums, derive name from common prefix
        if not enum_name:
            member_names = [
                child.spelling for child in cursor.get_children() if child.kind == CursorKind.ENUM_CONSTANT_DECL
            ]

            if member_names:
                # Find common prefix using the code generator's method
                common_prefix = self.code_generator._find_common_prefix(member_names)
                if common_prefix and len(common_prefix) > 2:
                    enum_name = common_prefix.rstrip("_")
                    if not enum_name:
                        # Will be assigned a unique name later
                        enum_name = None

        # Get underlying type for enum inheritance
        underlying_type = None
        if hasattr(cursor, "enum_type"):
            underlying_type = self.code_generator._map_enum_underlying_type(cursor.enum_type)

        # Collect members
        members = []
        for child in cursor.get_children():
            if child.kind == CursorKind.ENUM_CONSTANT_DECL:
                name = child.spelling
                value = child.enum_value
                members.append((name, value))

        if members:
            # Add to existing enum or create new entry
            if enum_name:
                if enum_name not in self.enum_members:
                    self.enum_members[enum_name] = (self.current_library, [], underlying_type)
                # Merge members, avoiding duplicates
                library, existing_members, existing_underlying_type = self.enum_members[enum_name]
                existing_member_names = {m[0] for m in existing_members}
                for member in members:
                    if member[0] not in existing_member_names:
                        existing_members.append(member)
                # Update underlying type if we have one and existing doesn't
                if underlying_type and not existing_underlying_type:
                    self.enum_members[enum_name] = (library, existing_members, underlying_type)
            else:
                # Anonymous enum - assign unique name
                anonymous_counter = 1
                while f"AnonymousEnum{anonymous_counter}" in self.enum_members:
                    anonymous_counter += 1
                enum_name = f"AnonymousEnum{anonymous_counter}"
                self.enum_members[enum_name] = (self.current_library, members, underlying_type)

    def _build_file_depth_map(self, tu, root_file: str, max_depth: Optional[int]) -> dict[str, int]:
        """Build a mapping of file paths to their include depth

        Args:
            tu: Translation unit
            root_file: Root header file path
            max_depth: Maximum include depth to process (None for infinite)

        Returns:
            Dictionary mapping absolute file paths to their depth level
        """
        file_depth = {str(Path(root_file).resolve()): 0}

        if max_depth == 0:
            return file_depth

        # If max_depth is None, use a very large number for infinite depth
        effective_max_depth = float("inf") if max_depth is None else max_depth

        # Collect all inclusion directives with their source file
        def collect_inclusions(cursor, inclusions):
            """Collect all INCLUSION_DIRECTIVE nodes"""
            if cursor.kind == CursorKind.INCLUSION_DIRECTIVE:
                source_file = cursor.location.file
                included_file = cursor.get_included_file()
                if source_file and included_file:
                    source_path = str(Path(source_file.name).resolve())
                    included_path = str(Path(included_file.name).resolve())
                    inclusions.append((source_path, included_path))

            for child in cursor.get_children():
                collect_inclusions(child, inclusions)

        # Collect all inclusions
        inclusions: list[tuple[str, str]] = []
        collect_inclusions(tu.cursor, inclusions)

        # Build depth map by processing inclusions level by level
        current_depth = 0
        while current_depth < effective_max_depth:
            # Find all files at current depth
            files_at_depth = {f for f, d in file_depth.items() if d == current_depth}
            if not files_at_depth:
                break

            # Find all files included by files at current depth
            for source_path, included_path in inclusions:
                if source_path in files_at_depth:
                    new_depth = current_depth + 1
                    if included_path not in file_depth or file_depth[included_path] > new_depth:
                        file_depth[included_path] = new_depth

            current_depth += 1

        return file_depth

    def generate(
        self,
        header_library_pairs: list[tuple[str, str]],
        output: str,
        include_dirs: Optional[list[str]] = None,
        include_depth: Optional[int] = None,
        ignore_missing: bool = False,
        library_class_names: Optional[dict[str, str]] = None,
        library_namespaces: Optional[dict[str, str]] = None,
        library_using_statements: Optional[dict[str, list[str]]] = None,
        visibility: str = "public",
        global_constants: Optional[list[tuple[str, str, str, bool]]] = None,
    ) -> dict[str, str]:
        """Generate C# bindings from C header file(s)

        Args:
            header_library_pairs: List of (header_file, library_name) tuples
            output: Output directory for generated files (required)
            include_dirs: List of directories to search for included headers
            include_depth: How deep to process included files (0=only input files, 1=direct includes, etc.; None=infinite)
            library_class_names: Dict mapping library names to custom class names (defaults to NativeMethods)
            library_namespaces: Dict mapping library names to custom namespaces
            library_using_statements: Dict mapping library names to lists of using statements
            visibility: Visibility modifier for generated code ("public" or "internal")
            global_constants: List of (name, pattern, type) tuples for macro extraction, applied to all libraries
        """
        # Store visibility setting
        self.visibility = visibility

        # Initialize code generator with visibility
        self.code_generator = CodeGenerator(self.type_mapper, visibility)

        # Store library class names
        self.library_class_names = library_class_names or {}

        # Store library namespaces
        self.library_namespaces = library_namespaces or {}

        # Store library using statements
        self.library_using_statements = library_using_statements or {}

        # Store global constants
        self.global_constants = global_constants or []

        # Clear previous state
        self._clear_state()

        if include_dirs is None:
            include_dirs = []

        # Build clang arguments
        clang_args = ["-x", "c"]
        for include_dir in include_dirs:
            clang_args.append(f"-I{include_dir}")

        # Add system include paths so clang can find standard headers
        # These paths are typical locations for system headers
        import subprocess

        try:
            # Try to get system include paths from clang itself
            result = subprocess.run(["clang", "-E", "-v", "-"], input=b"", capture_output=True, text=False, timeout=2)
            stderr = result.stderr.decode("utf-8", errors="ignore")
            in_includes = False
            for line in stderr.split("\n"):
                if "#include <...> search starts here:" in line:
                    in_includes = True
                    continue
                if in_includes:
                    if line.startswith("End of search list"):
                        break
                    # Extract path from line like " /usr/include"
                    path = line.strip()
                    if path and path.startswith("/"):
                        clang_args.append(f"-I{path}")
        except Exception:
            # Fallback to common paths if clang query fails
            # Don't print errors - this is a best-effort attempt
            for path in ["/usr/lib/clang/21/include", "/usr/local/include", "/usr/include"]:
                clang_args.append(f"-I{path}")

        # Parse each header file
        index = clang.cindex.Index.create()

        # Parse options to get detailed preprocessing info (for include directives)
        parse_options = clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD

        successfully_processed = 0

        for header_file, library_name in header_library_pairs:
            if not Path(header_file).exists():
                if ignore_missing:
                    print(f"Warning: Header file not found: {header_file}", file=sys.stderr)
                    continue
                else:
                    print(f"Error: Header file not found: {header_file}", file=sys.stderr)
                    raise FileNotFoundError(f"Header file not found: {header_file}")

            self.source_file = header_file
            self.current_library = library_name
            print(f"Processing: {header_file} -> {library_name}")
            if include_dirs:
                print(f"Include directories: {', '.join(include_dirs)}")
            if include_depth is not None:
                print(f"Include depth: {include_depth}")
            else:
                print("Include depth: infinite")

            tu = index.parse(header_file, args=clang_args, options=parse_options)

            # Check for parse errors (warnings don't stop processing)
            has_fatal_errors = False
            error_messages = []
            for diag in tu.diagnostics:
                if diag.severity >= clang.cindex.Diagnostic.Error:
                    error_msg = f"Error in {header_file}: {diag.spelling}"
                    print(error_msg, file=sys.stderr)
                    error_messages.append(diag.spelling)
                if diag.severity >= clang.cindex.Diagnostic.Fatal:
                    has_fatal_errors = True

            if has_fatal_errors:
                print(f"Fatal errors in {header_file}, cannot continue", file=sys.stderr)
                if error_messages:
                    raise RuntimeError(
                        f"Fatal parsing errors in {header_file}. Errors: {'; '.join(error_messages)}. Check include directories and header file accessibility."
                    )
                else:
                    raise RuntimeError(
                        f"Fatal parsing errors in {header_file}. Check include directories and header file accessibility."
                    )

            # Build file depth map and update allowed files
            file_depth_map = self._build_file_depth_map(tu, header_file, include_depth)
            self.allowed_files.update(file_depth_map.keys())

            if include_depth != 0 and len(file_depth_map) > 1:
                depth_str = str(include_depth) if include_depth is not None else "infinite"
                print(f"Processing {len(file_depth_map)} file(s) (depth {depth_str}):")
                for file_path, depth in sorted(file_depth_map.items(), key=lambda x: x[1]):
                    print(f"  [depth {depth}] {Path(file_path).name}")

            # Extract macros if global constants are defined
            if self.global_constants:
                if library_name not in self.captured_macros:
                    self.captured_macros[library_name] = {}

                # Collect all patterns from global constants
                patterns = []
                for const_name, const_pattern, const_type, const_flags in self.global_constants:
                    patterns.append(const_pattern)

                # Extract macros from all files in the depth map
                for file_path in file_depth_map.keys():
                    if not self._is_system_header(file_path):
                        file_macros = self._extract_macros_from_file(file_path, patterns)
                        self.captured_macros[library_name].update(file_macros)

                if self.captured_macros[library_name]:
                    print(f"Captured {len(self.captured_macros[library_name])} macro(s) for {library_name}")

            # Pre-scan for opaque types before processing functions
            self.prescan_opaque_types(tu.cursor)

            # Process the AST
            self.process_cursor(tu.cursor)

            # Only count as successfully processed after parsing succeeds
            successfully_processed += 1

        # Check if any files were successfully processed
        if successfully_processed == 0 and not ignore_missing:
            header_files = [pair[0] for pair in header_library_pairs]
            raise RuntimeError(
                f"No header files could be processed successfully. Files attempted: {', '.join(header_files)}. This usually indicates missing include directories or inaccessible header files."
            )

        # Generate merged enums from collected members
        for original_enum_name, (library, members, underlying_type) in sorted(self.enum_members.items()):
            if members:
                # Apply rename to enum name
                enum_name = self.type_mapper.apply_rename(original_enum_name)

                # Add inheritance clause if underlying type is not default 'int'
                inheritance_clause = ""
                if underlying_type and underlying_type != "int":
                    inheritance_clause = f" : {underlying_type}"

                values_str = "\n".join([f"    {name} = {value}," for name, value in members])
                code = f"""{self.visibility} enum {enum_name}{inheritance_clause}
{{
{values_str}
}}
"""
                self._add_to_library_collection(self.generated_enums, library, code)

        # Generate enums from captured macros using global constants
        for library_name in self.captured_macros:
            for const_name, const_pattern, const_type, const_flags in self.global_constants:
                # Get all macros matching this pattern
                matching_macros = {}
                for macro_name, macro_value in self.captured_macros[library_name].items():
                    if re.fullmatch(const_pattern, macro_name):
                        matching_macros[macro_name] = macro_value

                if matching_macros:
                    # Apply rename rules to the enum name and member names
                    enum_name = self.type_mapper.apply_rename(const_name)

                    # Build enum members with renamed names
                    members = []
                    for macro_name, macro_value in sorted(matching_macros.items()):
                        renamed_member = self.type_mapper.apply_rename(macro_name)
                        members.append(f"    {renamed_member} = unchecked(({const_type})({macro_value})),")

                    members_str = "\n".join(members)

                    # Generate enum with specified type and optional [Flags] attribute
                    flags_attr = "[Flags]\n" if const_flags else ""
                    type_clause = f" : {const_type}" if const_type != "int" else ""
                    code = f"""{flags_attr}{self.visibility} enum {enum_name}{type_clause}
{{
{members_str}
}}
"""
                    self._add_to_library_collection(self.generated_enums, library_name, code)

        return self._generate_multi_file_output(output)

    def _generate_multi_file_output(self, output: str) -> dict[str, str]:
        """Generate multiple files, one per library"""
        if not output:
            raise ValueError("Output directory must be specified")

        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        # Get all libraries
        all_libraries = set()
        all_libraries.update(self.generated_enums.keys())
        all_libraries.update(self.generated_structs.keys())
        all_libraries.update(self.generated_unions.keys())
        all_libraries.update(self.generated_functions.keys())

        file_contents = {}

        # Create bindings.cs file with assembly attribute and default namespace
        bindings_content = OutputBuilder.build(
            namespace="Bindings",
            enums=[],
            structs=[],
            unions=[],
            functions=[],
            class_name=NATIVE_METHODS_CLASS,
            include_assembly_attribute=True,
            visibility=self.visibility,
        )
        bindings_file = output_path / "bindings.cs"
        bindings_file.write_text(bindings_content)
        file_contents["bindings.cs"] = bindings_content
        print(f"Generated assembly bindings: {bindings_file}")

        for library in sorted(all_libraries):
            # Get items for this library
            enums = self.generated_enums.get(library, [])
            structs = self.generated_structs.get(library, [])
            unions = self.generated_unions.get(library, [])
            functions = self.generated_functions.get(library, [])

            # Skip empty libraries
            if not any([enums, structs, unions, functions]):
                continue

            # Generate output for this library (without assembly attribute)
            class_name = self.library_class_names.get(library, NATIVE_METHODS_CLASS)
            library_namespace = self.library_namespaces.get(library, DEFAULT_NAMESPACE)
            library_using = self.library_using_statements.get(library, [])
            output = OutputBuilder.build(
                namespace=library_namespace,
                enums=enums,
                structs=structs,
                unions=unions,
                functions=functions,
                class_name=class_name,
                include_assembly_attribute=False,
                using_statements=library_using,
                visibility=self.visibility,
            )

            # Write to library-specific file
            library_file = output_path / f"{library}.cs"
            library_file.write_text(output)
            file_contents[f"{library}.cs"] = output

            print(f"Generated bindings for {library}: {library_file}")

        return file_contents
