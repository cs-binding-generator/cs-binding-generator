"""
Code generation functions for C# bindings
"""

from clang.cindex import CursorKind, TypeKind
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
        
        # Skip variadic functions (not supported in LibraryImport)
        # Note: Only FUNCTIONPROTO types can be checked for variadicity
        if cursor.type.kind == TypeKind.FUNCTIONPROTO:
            if cursor.type.is_function_variadic():
                return ""  # Skip variadic functions
        
        # Build parameter list
        params = []
        for arg in cursor.get_arguments():
            arg_type = self.type_mapper.map_type(arg.type)
            arg_name = arg.spelling or f"param{len(params)}"
            # Escape C# keywords in parameter names
            arg_name = self._escape_keyword(arg_name)
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
        
        # Skip anonymous/unnamed structs (they often appear in unions)
        if not struct_name or "unnamed" in struct_name or "::" in struct_name:
            return ""
        
        # Collect fields
        fields = []
        for field in cursor.get_children():
            if field.kind == CursorKind.FIELD_DECL:
                field_type = self.type_mapper.map_type(field.type)
                field_name = field.spelling
                
                # Skip fields with invalid types (anonymous unions/structs)
                if not field_type or "unnamed" in field_type or "::" in field_type:
                    continue
                
                # Skip unnamed fields (anonymous unions/structs)
                if not field_name:
                    continue
                
                # Escape C# keywords
                field_name = self._escape_keyword(field_name)
                
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
    
    @staticmethod
    def _escape_keyword(name: str) -> str:
        """Escape C# keywords by prefixing with @"""
        # C# keywords that might appear as identifiers
        csharp_keywords = {
            'abstract', 'as', 'base', 'bool', 'break', 'byte', 'case', 'catch',
            'char', 'checked', 'class', 'const', 'continue', 'decimal', 'default',
            'delegate', 'do', 'double', 'else', 'enum', 'event', 'explicit', 'extern',
            'false', 'finally', 'fixed', 'float', 'for', 'foreach', 'goto', 'if',
            'implicit', 'in', 'int', 'interface', 'internal', 'is', 'lock', 'long',
            'namespace', 'new', 'null', 'object', 'operator', 'out', 'override',
            'params', 'private', 'protected', 'public', 'readonly', 'ref', 'return',
            'sbyte', 'sealed', 'short', 'sizeof', 'stackalloc', 'static', 'string',
            'struct', 'switch', 'this', 'throw', 'true', 'try', 'typeof', 'uint',
            'ulong', 'unchecked', 'unsafe', 'ushort', 'using', 'virtual', 'void',
            'volatile', 'while'
        }
        if name.lower() in csharp_keywords:
            return f"@{name}"
        return name
    
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
        
        # Functions class - mark as unsafe for pointer support
        if functions:
            parts.append(f"public static unsafe partial class {class_name}")
            parts.append("{")
            parts.extend(functions)
            parts.append("}")
        
        return "\n".join(parts)
