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
        
        # Skip if return type cannot be mapped
        if result_type is None:
            return ""
        
        # Skip variadic functions (not supported in LibraryImport)
        # Note: Only FUNCTIONPROTO types can be checked for variadicity
        if cursor.type.kind == TypeKind.FUNCTIONPROTO:
            if cursor.type.is_function_variadic():
                return ""  # Skip variadic functions
        
        # Build parameter list with marshalling attributes
        params = []
        for arg in cursor.get_arguments():
            arg_type = self.type_mapper.map_type(arg.type)
            # Skip functions with unmappable parameter types (like va_list)
            if arg_type is None:
                return ""
            arg_name = arg.spelling or f"param{len(params)}"
            # Escape C# keywords in parameter names
            arg_name = self._escape_keyword(arg_name)
            
            # Add marshalling attributes for bool parameters
            if arg_type == "bool":
                params.append(f"[MarshalAs(UnmanagedType.I1)] {arg_type} {arg_name}")
            else:
                params.append(f"{arg_type} {arg_name}")
        
        params_str = ", ".join(params) if params else ""
        
        # Add return value marshalling attribute for bool
        return_marshal = ""
        if result_type == "bool":
            return_marshal = "    [return: MarshalAs(UnmanagedType.I1)]\n"
        
        # Generate LibraryImport attribute and method with StringMarshalling
        code = f'''    [LibraryImport("{self.library_name}", EntryPoint = "{func_name}", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
{return_marshal}    public static partial {result_type} {func_name}({params_str});
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
                field_name = field.spelling
                
                # Skip unnamed fields (anonymous unions/structs)
                if not field_name:
                    continue
                
                # Escape C# keywords
                field_name = self._escape_keyword(field_name)
                
                # Check if this is a constant array (fixed-size array in struct)
                if field.type.kind == TypeKind.CONSTANTARRAY:
                    element_type = field.type.get_array_element_type()
                    array_size = field.type.get_array_size()
                    element_csharp = self.type_mapper.map_type(element_type)
                    
                    # Skip if element type cannot be mapped
                    if not element_csharp:
                        continue
                    
                    # Use fixed buffer for primitive types in unsafe struct
                    # For now, manually expand arrays as individual fields
                    for i in range(array_size):
                        fields.append(f"    public {element_csharp} {field_name}_{i};")
                else:
                    field_type = self.type_mapper.map_type(field.type)
                    
                    # Skip fields with invalid types (anonymous unions/structs)
                    if not field_type or "unnamed" in field_type or "::" in field_type:
                        continue
                    
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
