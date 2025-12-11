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
        self.anonymous_enum_counter = 0
    
    def generate_function(self, cursor) -> str:
        """Generate C# LibraryImport for a function"""
        func_name = cursor.spelling
        result_type = self.type_mapper.map_type(cursor.result_type, is_return_type=True)
        
        # Skip if return type cannot be mapped
        if result_type is None:
            return ""
        
        # Check if this returns a char* (now mapped to nuint)
        is_char_pointer_return = self._is_char_pointer(cursor.result_type)
        
        # Check if this returns a struct by value (not allowed in LibraryImport)
        # LibraryImport cannot return structs by value, only primitives or pointers
        is_struct_return = self._is_struct_return(cursor.result_type)
        struct_return_type = result_type  # Save the original struct type name
        if is_struct_return:
            result_type = "nuint"  # Return as nuint pointer instead
        
        # Skip variadic functions (not supported in LibraryImport)
        # Note: Only FUNCTIONPROTO types can be checked for variadicity
        if cursor.type.kind == TypeKind.FUNCTIONPROTO:
            if cursor.type.is_function_variadic():
                return ""  # Skip variadic functions
        
        # Build parameter list with marshalling attributes
        # Also track which parameters are char** (nuint representing output string pointers)
        params = []
        char_double_ptr_params = []  # Track char** parameters by index and info
        for i, arg in enumerate(cursor.get_arguments()):
            arg_type = self.type_mapper.map_type(arg.type, is_return_type=False)
            # Skip functions with unmappable parameter types (like va_list)
            if arg_type is None:
                return ""
            arg_name = arg.spelling or f"param{len(params)}"
            # Escape C# keywords in parameter names
            arg_name = self._escape_keyword(arg_name)
            
            # Check if this is a char** parameter (now mapped to nuint)
            if arg_type == "nuint" and self._is_char_double_pointer(arg.type):
                char_double_ptr_params.append({
                    'index': i,
                    'name': arg_name,
                    'original_type': arg.type
                })
            
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
        
        # Add helper function for char* return types
        if is_char_pointer_return:
            # Get parameter names for the helper function call
            param_names = []
            for arg in cursor.get_arguments():
                arg_name = arg.spelling or f"param{len(param_names)}"
                arg_name = self._escape_keyword(arg_name)
                param_names.append(arg_name)
            param_names_str = ", ".join(param_names) if param_names else ""
            
            code += f'''
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static string? {func_name}String({params_str})
    {{
        var ptr = {func_name}({param_names_str});
        return ptr == 0 ? null : Marshal.PtrToStringUTF8((nint)ptr);
    }}
'''
        
        # Add helper function for functions with char** parameters (output string pointers)
        if char_double_ptr_params:
            # Build new parameter list replacing nuint with out string? for char** params
            helper_params = []
            call_params = []
            setup_code = []
            cleanup_code = []
            
            for i, arg in enumerate(cursor.get_arguments()):
                arg_type = self.type_mapper.map_type(arg.type, is_return_type=False)
                if arg_type is None:
                    continue
                arg_name = arg.spelling or f"param{i}"
                arg_name = self._escape_keyword(arg_name)
                
                # Check if this parameter is a char** (nuint output parameter)
                is_char_dbl_ptr = any(p['index'] == i for p in char_double_ptr_params)
                
                if is_char_dbl_ptr:
                    # Replace with out string? parameter
                    helper_params.append(f"out string? {arg_name}")
                    # Add setup code for pointer variable
                    ptr_var = f"{arg_name}Ptr"
                    setup_code.append(f"        nuint {ptr_var} = 0;")
                    call_params.append(f"(nuint)(&{ptr_var})")
                    # Add cleanup code to marshal the pointer back to string
                    cleanup_code.append(f"""        if ({ptr_var} == 0)
        {{
            {arg_name} = null;
        }}
        else
        {{
            {arg_name} = Marshal.PtrToStringUTF8((nint){ptr_var});
        }}""")
                else:
                    # Keep parameter as-is
                    if arg_type == "bool":
                        helper_params.append(f"[MarshalAs(UnmanagedType.I1)] {arg_type} {arg_name}")
                    else:
                        helper_params.append(f"{arg_type} {arg_name}")
                    call_params.append(arg_name)
            
            helper_params_str = ", ".join(helper_params)
            call_params_str = ", ".join(call_params)
            setup_str = "\n".join(setup_code)
            cleanup_str = "\n".join(cleanup_code)
            
            return_statement = "return result;" if result_type != "void" else ""
            result_var = f"{result_type} result = " if result_type != "void" else ""
            
            code += f'''
    public static unsafe {result_type} {func_name}String({helper_params_str})
    {{
{setup_str}
        {result_var}{func_name}({call_params_str});
{cleanup_str}
        {return_statement}
    }}
'''
        
        # Add helper function for struct return types
        if is_struct_return:
            # Build parameters for helper (same as original)
            code += f'''
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static unsafe {struct_return_type} {func_name}Struct({params_str})
    {{
        var ptr = {func_name}({", ".join(arg.spelling or f"param{i}" for i, arg in enumerate(cursor.get_arguments())) if cursor.get_arguments() else ""});
        return Marshal.PtrToStructure<{struct_return_type}>((nint)ptr);
    }}
'''
        
        return code
    
    def _is_char_pointer(self, ctype) -> bool:
        """Check if a type is char* (pointer to char)"""
        if ctype.kind == TypeKind.POINTER:
            pointee = ctype.get_pointee()
            return pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U)
        return False
    
    def _is_char_double_pointer(self, ctype) -> bool:
        """Check if a type is char** (pointer to pointer to char)"""
        if ctype.kind == TypeKind.POINTER:
            pointee = ctype.get_pointee()
            if pointee.kind == TypeKind.POINTER:
                inner_pointee = pointee.get_pointee()
                return inner_pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U)
        return False
    
    def _is_struct_return(self, ctype) -> bool:
        """Check if a type is a struct/union returned by value"""
        # Check if it's a RECORD (struct/union) type that's not a pointer
        if ctype.kind == TypeKind.RECORD:
            return True
        # Also check ELABORATED types (typedef'd structs)
        if ctype.kind == TypeKind.ELABORATED:
            canonical = ctype.get_canonical()
            return canonical.kind == TypeKind.RECORD
        return False
    
    def generate_struct(self, cursor) -> str:
        """Generate C# struct with explicit layout"""
        struct_name = cursor.spelling
        
        # Skip anonymous/unnamed structs (they often appear in unions)
        if not struct_name or "unnamed" in struct_name or "::" in struct_name:
            return ""
        
        # Collect fields with their offsets
        fields = []
        for field in cursor.get_children():
            if field.kind == CursorKind.FIELD_DECL:
                field_name = field.spelling
                
                # Skip unnamed fields (anonymous unions/structs)
                if not field_name:
                    continue
                
                # Escape C# keywords
                field_name = self._escape_keyword(field_name)
                
                # Get field offset in bytes (libclang returns bits)
                offset_bits = field.get_field_offsetof()
                offset_bytes = offset_bits // 8
                
                # Check if this is a constant array (fixed-size array in struct)
                if field.type.kind == TypeKind.CONSTANTARRAY:
                    element_type = field.type.get_array_element_type()
                    array_size = field.type.get_array_size()
                    element_csharp = self.type_mapper.map_type(element_type)
                    
                    # Skip if element type cannot be mapped
                    if not element_csharp:
                        continue
                    
                    # Get element size (assume byte-sized elements for now)
                    # For proper alignment, we need to know the element size
                    element_size = element_type.get_size()  # size in bytes
                    
                    # Expand arrays as individual fields with proper offsets
                    for i in range(array_size):
                        field_offset = offset_bytes + (i * element_size)
                        fields.append(f"    [FieldOffset({field_offset})]\n    public {element_csharp} {field_name}_{i};")
                else:
                    field_type = self.type_mapper.map_type(field.type, is_struct_field=True)
                    
                    # Skip fields with invalid types (anonymous unions/structs)
                    if not field_type or "unnamed" in field_type or "::" in field_type:
                        continue
                    
                    fields.append(f"    [FieldOffset({offset_bytes})]\n    public {field_type} {field_name};")
        
        if not fields:
            return ""
        
        fields_str = "\n".join(fields)
        
        code = f'''[StructLayout(LayoutKind.Explicit)]
public unsafe struct {struct_name}
{{
{fields_str}
}}
'''
        return code
    
    def generate_opaque_type(self, type_name: str) -> str:
        """Generate C# struct for opaque handle types (empty structs used as pointers)"""
        if not type_name or "unnamed" in type_name or "::" in type_name:
            return ""
        
        # Generate an empty struct that can be used as a type-safe handle
        # Note: Cannot use readonly because these are used with unsafe pointers
        code = f'''public struct {type_name}
{{
}}
'''
        return code
    
    def generate_union(self, cursor) -> str:
        """Generate C# struct representing a union using LayoutKind.Explicit"""
        union_name = cursor.spelling
        
        # Skip anonymous/unnamed unions
        if not union_name or "unnamed" in union_name or "::" in union_name:
            return ""
        
        # Collect fields - all starting at offset 0 for union
        fields = []
        for field in cursor.get_children():
            if field.kind == CursorKind.FIELD_DECL:
                field_name = field.spelling
                
                # Skip unnamed fields
                if not field_name:
                    continue
                
                # Escape C# keywords
                field_name = self._escape_keyword(field_name)
                
                # Check if this is a constant array (fixed-size array in union)
                if field.type.kind == TypeKind.CONSTANTARRAY:
                    element_type = field.type.get_array_element_type()
                    array_size = field.type.get_array_size()
                    element_csharp = self.type_mapper.map_type(element_type)
                    
                    # Skip if element type cannot be mapped
                    if not element_csharp:
                        continue
                    
                    # Get element size
                    element_size = element_type.get_size()
                    
                    # Expand arrays as individual fields, all starting at offset 0 (union behavior)
                    for i in range(array_size):
                        field_offset = i * element_size
                        fields.append(f"    [FieldOffset({field_offset})]\n    public {element_csharp} {field_name}_{i};")
                else:
                    field_type = self.type_mapper.map_type(field.type, is_struct_field=True)
                    
                    # Skip fields with invalid types
                    if not field_type or "unnamed" in field_type or "::" in field_type:
                        continue
                    
                    # All union fields start at offset 0
                    fields.append(f"    [FieldOffset(0)]\n    public {field_type} {field_name};")
        
        if not fields:
            return ""
        
        fields_str = "\n".join(fields)
        
        code = f'''[StructLayout(LayoutKind.Explicit)]
public unsafe struct {union_name}
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
        enum_name = cursor.spelling
        
        # Filter out invalid enum names (anonymous enums with full display name)
        if enum_name and ("unnamed" in enum_name or "(" in enum_name or "::" in enum_name):
            enum_name = None
        
        # Collect enum values
        values = []
        for child in cursor.get_children():
            if child.kind == CursorKind.ENUM_CONSTANT_DECL:
                name = child.spelling
                value = child.enum_value
                values.append(f"    {name} = {value},")
        
        if not values:
            return ""
        
        # Generate name for anonymous enum
        if not enum_name:
            # Try to derive name from common prefix of members
            member_names = [child.spelling for child in cursor.get_children() 
                          if child.kind == CursorKind.ENUM_CONSTANT_DECL]
            
            if member_names:
                # Find common prefix
                common_prefix = self._find_common_prefix(member_names)
                # Remove trailing underscore and convert to PascalCase
                if common_prefix and len(common_prefix) > 2:
                    enum_name = common_prefix.rstrip('_')
                    # If it ends up empty after stripping, use counter
                    if not enum_name:
                        self.anonymous_enum_counter += 1
                        enum_name = f"AnonymousEnum{self.anonymous_enum_counter}"
                else:
                    self.anonymous_enum_counter += 1
                    enum_name = f"AnonymousEnum{self.anonymous_enum_counter}"
            else:
                self.anonymous_enum_counter += 1
                enum_name = f"AnonymousEnum{self.anonymous_enum_counter}"
        
        values_str = "\n".join(values)
        
        code = f'''public enum {enum_name}
{{
{values_str}
}}
'''
        return code
    
    def _find_common_prefix(self, strings: list[str]) -> str:
        """Find common prefix of a list of strings"""
        if not strings:
            return ""
        
        # Find the shortest string
        min_len = min(len(s) for s in strings)
        
        # Check each character position
        for i in range(min_len):
            char = strings[0][i]
            if not all(s[i] == char for s in strings):
                return strings[0][:i]
        
        return strings[0][:min_len]


class OutputBuilder:
    """Builds the final C# output file"""
    
    @staticmethod
    def build(namespace: str, enums: list[str], structs: list[str], 
              unions: list[str], functions: list[str], class_name: str = "NativeMethods") -> str:
        """Build the final C# output"""
        parts = []
        
        # Usings (non-global)
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
        
        # Unions (represented as structs with explicit layout)
        if unions:
            parts.extend(unions)
            parts.append("")
        
        # Functions class - mark as unsafe for pointer support
        if functions:
            parts.append(f"public static unsafe partial class {class_name}")
            parts.append("{")
            parts.extend(functions)
            parts.append("}")
        
        return "\n".join(parts)
