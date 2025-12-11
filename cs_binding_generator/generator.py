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
    
    def process_cursor(self, cursor):
        """Recursively process AST nodes"""
        # Only process items in allowed files (based on include depth)
        if cursor.location.file:
            file_path = str(cursor.location.file)
            if file_path not in self.allowed_files:
                return
        
        if cursor.kind == CursorKind.FUNCTION_DECL:
            code = self.code_generator.generate_function(cursor)
            if code:
                self.generated_functions.append(code)
        
        elif cursor.kind == CursorKind.STRUCT_DECL:
            if cursor.is_definition():
                code = self.code_generator.generate_struct(cursor)
                if code:
                    self.generated_structs.append(code)
        
        elif cursor.kind == CursorKind.ENUM_DECL:
            if cursor.is_definition():
                code = self.code_generator.generate_enum(cursor)
                if code:
                    self.generated_enums.append(code)
        
        # Recurse into children
        for child in cursor.get_children():
            self.process_cursor(child)
    
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
            
            # Check for parse errors
            has_errors = False
            for diag in tu.diagnostics:
                if diag.severity >= clang.cindex.Diagnostic.Error:
                    print(f"Error in {header_file}: {diag.spelling}", file=sys.stderr)
                    has_errors = True
            
            if has_errors:
                continue
            
            # Build file depth map and update allowed files
            file_depth_map = self._build_file_depth_map(tu, header_file, include_depth)
            self.allowed_files.update(file_depth_map.keys())
            
            if include_depth > 0 and len(file_depth_map) > 1:
                print(f"Processing {len(file_depth_map)} file(s) (depth {include_depth}):")
                for file_path, depth in sorted(file_depth_map.items(), key=lambda x: x[1]):
                    print(f"  [depth {depth}] {Path(file_path).name}")
            
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
