"""
Main C# bindings generator orchestration
"""

import sys
from pathlib import Path
import clang.cindex
from clang.cindex import CursorKind, TypeKind

from .type_mapper import TypeMapper
from .code_generators import CodeGenerator, OutputBuilder
from .constants import NATIVE_METHODS_CLASS


class CSharpBindingsGenerator:
    """Main orchestrator for generating C# bindings from C headers"""
    
    def __init__(self):
        self.type_mapper = TypeMapper()
        self.code_generator = CodeGenerator(self.type_mapper)
        
        # Store generated items by library
        self.generated_functions = {}  # library -> [functions]
        self.generated_structs = {}    # library -> [structs] 
        self.generated_unions = {}     # library -> [unions]
        self.generated_enums = {}      # library -> [enums]
        self.source_file = None
        self.allowed_files = set()  # Files allowed based on include depth
        
        # Track what we've already generated to avoid duplicates
        self.seen_functions = set()  # (name, location)
        self.seen_structs = set()    # (name, location)
        self.seen_unions = set()     # (name, location)
        self.enum_members = {}       # name -> (library, list of (member_name, value) tuples, underlying_type)
    
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
        self.source_file = None
        self.allowed_files.clear()
    
    def _is_system_header(self, file_path: str) -> bool:
        """Check if a file path is a system header that should be excluded"""
        path = Path(file_path).resolve()
        path_str = str(path)
        
        # Standard C library headers to exclude  - check filename first
        c_std_headers = {
            'assert.h', 'complex.h', 'ctype.h', 'errno.h', 'fenv.h', 'float.h',
            'inttypes.h', 'iso646.h', 'limits.h', 'locale.h', 'math.h', 'setjmp.h',
            'signal.h', 'stdalign.h', 'stdarg.h', 'stdatomic.h', 'stdbool.h', 
            'stddef.h', 'stdint.h', 'stdio.h', 'stdlib.h', 'stdnoreturn.h',
            'string.h', 'tgmath.h', 'threads.h', 'time.h', 'uchar.h', 'wchar.h',
            'wctype.h', 'alloca.h'
        }
        
        filename = path.name
        if filename in c_std_headers:
            return True
        
        # System directories to exclude entirely
        system_paths = [
            '/usr/include/c++',
            '/usr/include/x86_64-linux-gnu',
            '/usr/include/aarch64-linux-gnu',
            '/usr/lib/gcc',
            '/usr/lib/clang',
            '/usr/local/include',
        ]
        
        if any(path_str.startswith(sys_path) for sys_path in system_paths):
            return True
        
        # System subdirectories under /usr/include to exclude
        if path_str.startswith('/usr/include/'):
            relative = path_str[len('/usr/include/'):]
            first_part = relative.split('/')[0] if '/' in relative else ''
            
            system_subdirs = {'sys', 'bits', 'gnu', 'asm', 'asm-generic', 'linux', 
                            'arpa', 'net', 'netinet', 'rpc', 'scsi', 'protocols'}
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
            # Check if we've already generated this function
            # In multi-file mode, use global deduplication to avoid duplicate partial methods
            # In single-file mode, use library-specific deduplication for flexibility
            if self.multi_file:
                func_key = cursor.spelling  # Global deduplication by function name
                if func_key not in self.seen_functions:
                    code = self.code_generator.generate_function(cursor, self.current_library)
                    if code:
                        self._add_to_library_collection(self.generated_functions, self.current_library, code)
                        self.seen_functions.add(func_key)
            else:
                # Library-specific deduplication for single-file mode
                library_func_key = (self.current_library, cursor.spelling)
                if library_func_key not in self.seen_functions:
                    code = self.code_generator.generate_function(cursor, self.current_library)
                    if code:
                        self._add_to_library_collection(self.generated_functions, self.current_library, code)
                        self.seen_functions.add(library_func_key)
        
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
                # Check if we've already generated this struct
                # In multi-file mode, use global deduplication to avoid duplicate struct definitions
                # In single-file mode, use library-specific deduplication for flexibility
                if self.multi_file:
                    struct_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                    if struct_key not in self.seen_structs:
                        code = self.code_generator.generate_struct(cursor)
                        if code:
                            self._add_to_library_collection(self.generated_structs, self.current_library, code)
                            self.seen_structs.add(struct_key)
                            # Also mark as seen by name only to prevent opaque type generation
                            if cursor.spelling:
                                self.seen_structs.add((cursor.spelling, None, None))
                else:
                    # Library-specific deduplication for single-file mode
                    struct_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                    library_struct_key = (self.current_library, struct_key)
                    if library_struct_key not in self.seen_structs:
                        code = self.code_generator.generate_struct(cursor)
                        if code:
                            self._add_to_library_collection(self.generated_structs, self.current_library, code)
                            self.seen_structs.add(library_struct_key)
                            # Also mark as seen by name only to prevent opaque type generation
                            if cursor.spelling:
                                self.seen_structs.add((self.current_library, (cursor.spelling, None, None)))
        
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
                # Check if we've already generated this union
                # In multi-file mode, use global deduplication to avoid duplicate union definitions
                # In single-file mode, use library-specific deduplication for flexibility
                if self.multi_file:
                    union_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                    if union_key not in self.seen_unions:
                        code = self.code_generator.generate_union(cursor)
                        if code:
                            self._add_to_library_collection(self.generated_unions, self.current_library, code)
                            self.seen_unions.add(union_key)
                else:
                    # Library-specific deduplication for single-file mode
                    union_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                    library_union_key = (self.current_library, union_key)
                    if library_union_key not in self.seen_unions:
                        code = self.code_generator.generate_union(cursor)
                        if code:
                            self._add_to_library_collection(self.generated_unions, self.current_library, code)
                            self.seen_unions.add(library_union_key)
        
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
                if child.kind == CursorKind.TYPE_REF and child.spelling and 'struct ' in str(child.type.spelling):
                    # This is an opaque typedef like: typedef struct SDL_Window SDL_Window;
                    if type_name and type_name not in ['size_t', 'ssize_t', 'ptrdiff_t', 'intptr_t', 'uintptr_t', 'wchar_t']:
                        struct_key = (type_name, str(cursor.location.file), cursor.location.line)
                        if self.multi_file:
                            # Global deduplication in multi-file mode
                            if struct_key not in self.seen_structs:
                                code = self.code_generator.generate_opaque_type(type_name)
                                if code:
                                    self._add_to_library_collection(self.generated_structs, self.current_library, code)
                                    self.seen_structs.add(struct_key)
                                    self.seen_structs.add((type_name, None, None))
                                    # Register as opaque type for pointer handling
                                    self.type_mapper.opaque_types.add(type_name)
                        else:
                            # Library-specific deduplication in single-file mode
                            library_struct_key = (self.current_library, struct_key)
                            if library_struct_key not in self.seen_structs:
                                code = self.code_generator.generate_opaque_type(type_name)
                                if code:
                                    self._add_to_library_collection(self.generated_structs, self.current_library, code)
                                    self.seen_structs.add(library_struct_key)
                                    self.seen_structs.add((self.current_library, (type_name, None, None)))
                                    # Register as opaque type for pointer handling
                                    self.type_mapper.opaque_types.add(type_name)
                elif child.kind == CursorKind.STRUCT_DECL and not child.is_definition() and child.spelling:
                    # Direct forward declaration
                    struct_key = (child.spelling, str(cursor.location.file), cursor.location.line)
                    if self.multi_file:
                        # Global deduplication in multi-file mode
                        if struct_key not in self.seen_structs:
                            code = self.code_generator.generate_opaque_type(child.spelling)
                            if code:
                                self._add_to_library_collection(self.generated_structs, self.current_library, code)
                                self.seen_structs.add(struct_key)
                                self.seen_structs.add((child.spelling, None, None))
                                # Register as opaque type for pointer handling
                                self.type_mapper.opaque_types.add(child.spelling)
                    else:
                        # Library-specific deduplication in single-file mode
                        library_struct_key = (self.current_library, struct_key)
                        if library_struct_key not in self.seen_structs:
                            code = self.code_generator.generate_opaque_type(child.spelling)
                            if code:
                                self._add_to_library_collection(self.generated_structs, self.current_library, code)
                                self.seen_structs.add(library_struct_key)
                                self.seen_structs.add((self.current_library, (child.spelling, None, None)))
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
                if child.kind == CursorKind.TYPE_REF and child.spelling and 'struct ' in str(child.type.spelling):
                    # This is an opaque typedef like: typedef struct SDL_Window SDL_Window;
                    if type_name and type_name not in ['size_t', 'ssize_t', 'ptrdiff_t', 'intptr_t', 'uintptr_t', 'wchar_t']:
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
            member_names = [child.spelling for child in cursor.get_children() 
                          if child.kind == CursorKind.ENUM_CONSTANT_DECL]
            
            if member_names:
                # Find common prefix using the code generator's method
                common_prefix = self.code_generator._find_common_prefix(member_names)
                if common_prefix and len(common_prefix) > 2:
                    enum_name = common_prefix.rstrip('_')
                    if not enum_name:
                        # Will be assigned a unique name later
                        enum_name = None
        
        # Get underlying type for enum inheritance
        underlying_type = None
        if hasattr(cursor, 'enum_type'):
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
    
    def _build_file_depth_map(self, tu, root_file: str, max_depth: int) -> dict[str, int]:
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
        effective_max_depth = float('inf') if max_depth is None else max_depth
        
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
        inclusions = []
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
    
    def generate(self, header_library_pairs: list[tuple[str, str]], output: str = None, 
                 namespace: str = "Bindings", include_dirs: list[str] = None,
                 include_depth: int = None, ignore_missing: bool = False, multi_file: bool = False) -> str | dict[str, str]:
        """Generate C# bindings from C header file(s)
        
        Args:
            header_files: List of C header files to process
            output: Optional output file path or directory (prints to stdout if not specified)
            namespace: C# namespace for generated code
            include_dirs: List of directories to search for included headers
            include_depth: How deep to process included files (0=only input files, 1=direct includes, etc.; None=infinite)
        """
        # Store multi_file setting for use in deduplication logic
        self.multi_file = multi_file
        
        # Clear previous state
        self._clear_state()
        
        if include_dirs is None:
            include_dirs = []
        
        # Build clang arguments
        clang_args = ['-x', 'c']
        for include_dir in include_dirs:
            clang_args.append(f'-I{include_dir}')
        
        # Add system include paths so clang can find standard headers
        # These paths are typical locations for system headers
        import subprocess
        try:
            # Try to get system include paths from clang itself
            result = subprocess.run(
                ['clang', '-E', '-v', '-'],
                input=b'',
                capture_output=True,
                text=False,
                timeout=2
            )
            stderr = result.stderr.decode('utf-8', errors='ignore')
            in_includes = False
            for line in stderr.split('\n'):
                if '#include <...> search starts here:' in line:
                    in_includes = True
                    continue
                if in_includes:
                    if line.startswith('End of search list'):
                        break
                    # Extract path from line like " /usr/include"
                    path = line.strip()
                    if path and path.startswith('/'):
                        clang_args.append(f'-I{path}')
        except Exception as e:
            # Fallback to common paths if clang query fails
            # Don't print errors - this is a best-effort attempt
            for path in ['/usr/lib/clang/21/include', '/usr/local/include', '/usr/include']:
                clang_args.append(f'-I{path}')
        
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
                print(f"Include depth: infinite")
            
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
                    raise RuntimeError(f"Fatal parsing errors in {header_file}. Errors: {'; '.join(error_messages)}. Check include directories and header file accessibility.")
                else:
                    raise RuntimeError(f"Fatal parsing errors in {header_file}. Check include directories and header file accessibility.")
            
            # Build file depth map and update allowed files
            file_depth_map = self._build_file_depth_map(tu, header_file, include_depth)
            self.allowed_files.update(file_depth_map.keys())
            
            if include_depth != 0 and len(file_depth_map) > 1:
                depth_str = str(include_depth) if include_depth is not None else 'infinite'
                print(f"Processing {len(file_depth_map)} file(s) (depth {depth_str}):")
                for file_path, depth in sorted(file_depth_map.items(), key=lambda x: x[1]):
                    print(f"  [depth {depth}] {Path(file_path).name}")
            
            # Pre-scan for opaque types before processing functions
            self.prescan_opaque_types(tu.cursor)
            
            # Process the AST
            self.process_cursor(tu.cursor)
            
            # Only count as successfully processed after parsing succeeds
            successfully_processed += 1
        
        # Check if any files were successfully processed
        if successfully_processed == 0 and not ignore_missing:
            header_files = [pair[0] for pair in header_library_pairs]
            raise RuntimeError(f"No header files could be processed successfully. Files attempted: {', '.join(header_files)}. This usually indicates missing include directories or inaccessible header files.")
        
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
                code = f'''public enum {enum_name}{inheritance_clause}
{{
{values_str}
}}
'''
                self._add_to_library_collection(self.generated_enums, library, code)
        
        if multi_file:
            return self._generate_multi_file_output(namespace, output)
        else:
            return self._generate_single_file_output(namespace, output)
    
    def _generate_single_file_output(self, namespace: str, output_file: str = None) -> str:
        """Generate single file output (original behavior)"""
        # Flatten all library collections into single lists
        all_enums = []
        all_structs = []
        all_unions = []
        all_functions = []
        
        for library_items in self.generated_enums.values():
            all_enums.extend(library_items)
        for library_items in self.generated_structs.values():
            all_structs.extend(library_items)
        for library_items in self.generated_unions.values():
            all_unions.extend(library_items)
        for library_items in self.generated_functions.values():
            all_functions.extend(library_items)
        
        # Generate the output
        output = OutputBuilder.build(
            namespace=namespace,
            enums=all_enums,
            structs=all_structs,
            unions=all_unions,
            functions=all_functions,
            class_name=NATIVE_METHODS_CLASS
        )
        
        # Apply post-processing to ensure all renames are applied
        output = self.apply_final_renames(output)
        
        # Write to file or return
        if output_file:
            Path(output_file).write_text(output)
            print(f"Generated bindings: {output_file}")
        else:
            print(output)
        
        return output
    
    def _generate_multi_file_output(self, namespace: str, output: str) -> dict[str, str]:
        """Generate multiple files, one per library"""
        if not output:
            raise ValueError("Output directory must be specified when using --multi flag")
        
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Get all libraries
        all_libraries = set()
        all_libraries.update(self.generated_enums.keys())
        all_libraries.update(self.generated_structs.keys())
        all_libraries.update(self.generated_unions.keys())
        all_libraries.update(self.generated_functions.keys())
        
        file_contents = {}
        
        # Create bindings.cs file with assembly attribute and namespace
        bindings_content = OutputBuilder.build(
            namespace=namespace,
            enums=[],
            structs=[],
            unions=[],
            functions=[],
            class_name=NATIVE_METHODS_CLASS,
            include_assembly_attribute=True
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
            output = OutputBuilder.build(
                namespace=namespace,
                enums=enums,
                structs=structs,
                unions=unions,
                functions=functions,
                class_name=NATIVE_METHODS_CLASS,
                include_assembly_attribute=False
            )
            
            # Apply post-processing to ensure all renames are applied
            output = self.apply_final_renames(output)
            
            # Write to library-specific file
            library_file = output_path / f"{library}.cs"
            library_file.write_text(output)
            file_contents[f"{library}.cs"] = output
            
            print(f"Generated bindings for {library}: {library_file}")
        
        return file_contents

    def apply_final_renames(self, output: str) -> str:
        """Apply all renames to the final output as a safety net"""
        # Get all renames from the type mapper
        renames = self.type_mapper.get_all_renames()
        
        import re
        
        for from_name, to_name, is_regex in renames:
            if is_regex:
                # For regex patterns, wrap in word boundaries and apply
                # Need to shift capture group numbers by 1 because we wrap pattern in outer group
                replacement = re.sub(r'\$(\d+)', lambda m: f'\\{int(m.group(1)) + 1}', to_name)
                pattern = r'\b(' + from_name + r')\b'
                output = re.sub(pattern, replacement, output)
            else:
                # Simple rename - replace type names as standalone types
                # Avoid replacements inside quoted strings (EntryPoint values) and larger identifiers
                pattern = r'(?<!")(?<![A-Za-z_])' + re.escape(from_name) + r'(?![A-Za-z0-9_])(?!")'
                output = re.sub(pattern, to_name, output)
                
                # Also handle pointer and double-pointer cases
                pointer_pattern = r'(?<!")(?<![A-Za-z_])' + re.escape(from_name) + r'(?=\*+)(?!")'
                output = re.sub(pointer_pattern, to_name, output)
        
        return output
