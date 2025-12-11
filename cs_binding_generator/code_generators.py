"""
Code generation functions for C# bindings
"""

from clang.cindex import CursorKind
from .type_mapper import TypeMapper


class CodeGenerator:
    """Generates C# code from libclang AST nodes"""
    
    def __init__(self, library_name: str, type_mapper: TypeMapper):
        self.library_name = library_name
        self.type_mapper = type_mapper
    
    def generate_function(self, cursor) -> str:
        """Generate C# LibraryImport for a function"""
        func_name = cursor.spelling
        result_type = self.type_mapper.map_type(cursor.result_type)
        
        # Build parameter list
        params = []
        for arg in cursor.get_arguments():
            arg_type = self.type_mapper.map_type(arg.type)
            arg_name = arg.spelling or f"param{len(params)}"
            params.append(f"{arg_type} {arg_name}")
        
        params_str = ", ".join(params) if params else ""
        
        # Generate LibraryImport attribute and method
        code = f'''    [LibraryImport("{self.library_name}", EntryPoint = "{func_name}")]
    public static partial {result_type} {func_name}({params_str});
'''
        return code
    
    def generate_struct(self, cursor) -> str:
        """Generate C# struct"""
        struct_name = cursor.spelling
        
        # Collect fields
        fields = []
        for field in cursor.get_children():
            if field.kind == CursorKind.FIELD_DECL:
                field_type = self.type_mapper.map_type(field.type)
                field_name = field.spelling
                fields.append(f"    public {field_type} {field_name};")
        
        if not fields:
            return ""
        
        fields_str = "\n".join(fields)
        
        code = f'''[StructLayout(LayoutKind.Sequential)]
public struct {struct_name}
{{
{fields_str}
}}
'''
        return code
    
    def generate_enum(self, cursor) -> str:
        """Generate C# enum"""
        enum_name = cursor.spelling or "AnonymousEnum"
        
        # Collect enum values
        values = []
        for child in cursor.get_children():
            if child.kind == CursorKind.ENUM_CONSTANT_DECL:
                name = child.spelling
                value = child.enum_value
                values.append(f"    {name} = {value},")
        
        if not values:
            return ""
        
        values_str = "\n".join(values)
        
        code = f'''public enum {enum_name}
{{
{values_str}
}}
'''
        return code


class OutputBuilder:
    """Builds the final C# output file"""
    
    @staticmethod
    def build(namespace: str, enums: list[str], structs: list[str], 
              functions: list[str], class_name: str = "NativeMethods") -> str:
        """Build the final C# output"""
        parts = []
        
        # Usings
        from .constants import REQUIRED_USINGS
        parts.extend(REQUIRED_USINGS)
        parts.append("")
        
        # Namespace
        parts.append(f"namespace {namespace};")
        parts.append("")
        
        # Enums
        if enums:
            parts.extend(enums)
            parts.append("")
        
        # Structs
        if structs:
            parts.extend(structs)
            parts.append("")
        
        # Functions class
        if functions:
            parts.append(f"public static partial class {class_name}")
            parts.append("{")
            parts.extend(functions)
            parts.append("}")
        
        return "\n".join(parts)
