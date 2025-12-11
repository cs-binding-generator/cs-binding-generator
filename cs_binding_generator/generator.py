"""
Main C# bindings generator orchestration
"""

import sys
from pathlib import Path
import clang.cindex
from clang.cindex import CursorKind

from .type_mapper import TypeMapper
from .code_generators import CodeGenerator, OutputBuilder
from .constants import NATIVE_METHODS_CLASS


class CSharpBindingsGenerator:
    """Main orchestrator for generating C# bindings from C headers"""
    
    def __init__(self, library_name: str):
        self.library_name = library_name
        self.type_mapper = TypeMapper()
        self.code_generator = CodeGenerator(library_name, self.type_mapper)
        
        self.generated_functions = []
        self.generated_structs = []
        self.generated_enums = []
        self.source_file = None
        self.allowed_files = set()  # Files allowed based on include depth
        
        # Track what we've already generated to avoid duplicates
        self.seen_functions = set()  # (name, location)
        self.seen_structs = set()    # (name, location)
        self.seen_enums = set()      # (name, location)
    
    def process_cursor(self, cursor):
        """Recursively process AST nodes"""
        # Only process items in allowed files (based on include depth)
        if cursor.location.file:
            file_path = str(cursor.location.file)
            if file_path not in self.allowed_files:
                return
        
        if cursor.kind == CursorKind.FUNCTION_DECL:
            # Check if we've already generated this function
            func_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
            if func_key not in self.seen_functions:
                code = self.code_generator.generate_function(cursor)
                if code:
                    self.generated_functions.append(code)
                    self.seen_functions.add(func_key)
        
        elif cursor.kind == CursorKind.STRUCT_DECL:
            if cursor.is_definition():
                # Check if we've already generated this struct
                struct_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                if struct_key not in self.seen_structs:
                    code = self.code_generator.generate_struct(cursor)
                    if code:
                        self.generated_structs.append(code)
                        self.seen_structs.add(struct_key)
                        # Also mark as seen by name only to prevent opaque type generation
                        if cursor.spelling:
                            self.seen_structs.add((cursor.spelling, None, None))
        
        elif cursor.kind == CursorKind.UNION_DECL:
            if cursor.is_definition():
                # Check if we've already generated this union
                union_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                if union_key not in self.seen_structs:  # Reuse seen_structs set for unions
                    code = self.code_generator.generate_union(cursor)
                    if code:
                        self.generated_structs.append(code)  # Add to structs list
                        self.seen_structs.add(union_key)
        
        elif cursor.kind == CursorKind.ENUM_DECL:
            if cursor.is_definition():
                # Check if we've already generated this enum
                enum_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                if enum_key not in self.seen_enums:
                    code = self.code_generator.generate_enum(cursor)
                    if code:
                        self.generated_enums.append(code)
                        self.seen_enums.add(enum_key)
        
        elif cursor.kind == CursorKind.TYPEDEF_DECL:
            # Handle opaque struct typedefs (e.g., typedef struct SDL_Window SDL_Window;)
            # These are used as handles in C APIs
            children = list(cursor.get_children())
            if len(children) == 1:
                child = children[0]
                type_name = cursor.spelling
                # Skip if already generated as a full struct
                if (type_name, None, None) in self.seen_structs:
                    return
                    
                # Check if it's a reference to a struct (TYPE_REF) or direct STRUCT_DECL
                if child.kind == CursorKind.TYPE_REF and child.spelling and 'struct ' in str(child.type.spelling):
                    # This is an opaque typedef like: typedef struct SDL_Window SDL_Window;
                    if type_name and type_name not in ['size_t', 'ssize_t', 'ptrdiff_t', 'intptr_t', 'uintptr_t', 'wchar_t']:
                        struct_key = (type_name, str(cursor.location.file), cursor.location.line)
                        if struct_key not in self.seen_structs:
                            code = self.code_generator.generate_opaque_type(type_name)
                            if code:
                                self.generated_structs.append(code)
                                self.seen_structs.add(struct_key)
                                self.seen_structs.add((type_name, None, None))
                                # Register as opaque type for pointer handling
                                self.type_mapper.opaque_types.add(type_name)
                elif child.kind == CursorKind.STRUCT_DECL and not child.is_definition() and child.spelling:
                    # Direct forward declaration
                    struct_key = (child.spelling, str(cursor.location.file), cursor.location.line)
                    if struct_key not in self.seen_structs:
                        code = self.code_generator.generate_opaque_type(child.spelling)
                        if code:
                            self.generated_structs.append(code)
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
    
    def _build_file_depth_map(self, tu, root_file: str, max_depth: int) -> dict[str, int]:
        """Build a mapping of file paths to their include depth
        
        Args:
            tu: Translation unit
            root_file: Root header file path
            max_depth: Maximum include depth to process
            
        Returns:
            Dictionary mapping absolute file paths to their depth level
        """
        file_depth = {str(Path(root_file).resolve()): 0}
        
        if max_depth == 0:
            return file_depth
        
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
        while current_depth < max_depth:
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
    
    def generate(self, header_files: list[str], output_file: str = None, 
                 namespace: str = "Bindings", include_dirs: list[str] = None,
                 include_depth: int = 0) -> str:
        """Generate C# bindings from C header file(s)
        
        Args:
            header_files: List of C header files to process
            output_file: Optional output file path (prints to stdout if not specified)
            namespace: C# namespace for generated code
            include_dirs: List of directories to search for included headers
            include_depth: How deep to process included files (0=only input files, 1=direct includes, etc.)
        """
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
        
        for header_file in header_files:
            if not Path(header_file).exists():
                print(f"Warning: Header file not found: {header_file}", file=sys.stderr)
                continue
            
            self.source_file = header_file
            print(f"Processing: {header_file}")
            if include_dirs:
                print(f"Include directories: {', '.join(include_dirs)}")
            if include_depth > 0:
                print(f"Include depth: {include_depth}")
            
            tu = index.parse(header_file, args=clang_args, options=parse_options)
            
            # Check for parse errors (warnings don't stop processing)
            has_fatal_errors = False
            for diag in tu.diagnostics:
                if diag.severity >= clang.cindex.Diagnostic.Error:
                    print(f"Error in {header_file}: {diag.spelling}", file=sys.stderr)
                if diag.severity >= clang.cindex.Diagnostic.Fatal:
                    has_fatal_errors = True
            
            if has_fatal_errors:
                print(f"Fatal errors in {header_file}, skipping", file=sys.stderr)
                continue
            
            # Build file depth map and update allowed files
            file_depth_map = self._build_file_depth_map(tu, header_file, include_depth)
            self.allowed_files.update(file_depth_map.keys())
            
            if include_depth > 0 and len(file_depth_map) > 1:
                print(f"Processing {len(file_depth_map)} file(s) (depth {include_depth}):")
                for file_path, depth in sorted(file_depth_map.items(), key=lambda x: x[1]):
                    print(f"  [depth {depth}] {Path(file_path).name}")
            
            # Pre-scan for opaque types before processing functions
            self.prescan_opaque_types(tu.cursor)
            
            # Process the AST
            self.process_cursor(tu.cursor)
        
        # Generate the output
        output = OutputBuilder.build(
            namespace=namespace,
            enums=self.generated_enums,
            structs=self.generated_structs,
            functions=self.generated_functions,
            class_name=NATIVE_METHODS_CLASS
        )
        
        # Write to file or return
        if output_file:
            Path(output_file).write_text(output)
            print(f"Generated bindings: {output_file}")
        else:
            print(output)
        
        return output
