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
    
    def process_cursor(self, cursor):
        """Recursively process AST nodes"""
        # Only process items in the main file (not includes)
        if cursor.location.file and str(cursor.location.file) != self.source_file:
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
    
    def generate(self, header_files: list[str], output_file: str = None, 
                 namespace: str = "Bindings") -> str:
        """Generate C# bindings from C header file(s)"""
        
        # Parse each header file
        index = clang.cindex.Index.create()
        
        for header_file in header_files:
            if not Path(header_file).exists():
                print(f"Warning: Header file not found: {header_file}", file=sys.stderr)
                continue
            
            self.source_file = header_file
            print(f"Processing: {header_file}")
            
            tu = index.parse(header_file, args=['-x', 'c'])
            
            # Check for parse errors
            has_errors = False
            for diag in tu.diagnostics:
                if diag.severity >= clang.cindex.Diagnostic.Error:
                    print(f"Error in {header_file}: {diag.spelling}", file=sys.stderr)
                    has_errors = True
            
            if has_errors:
                continue
            
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
