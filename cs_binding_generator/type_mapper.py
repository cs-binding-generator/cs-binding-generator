"""
Type mapping logic for converting C types to C# types
"""

from clang.cindex import TypeKind
from .constants import CSHARP_TYPE_MAP


class TypeMapper:
    """Maps C/libclang types to C# types"""
    
    def __init__(self):
        self.type_map = CSHARP_TYPE_MAP.copy()
        # Common typedef mappings (before resolving to canonical type)
        self.typedef_map = {
            'size_t': 'nuint',
            'ssize_t': 'nint',
            'ptrdiff_t': 'nint',
            'intptr_t': 'nint',
            'uintptr_t': 'nuint',
            'wchar_t': 'char',
        }
        # Track opaque types (empty structs used as handles)
        self.opaque_types = set()
    
    def map_type(self, ctype, is_return_type: bool = False) -> str:
        """Map C type to C# type
        
        Args:
            ctype: The libclang type to map
            is_return_type: True if this is a function return type (affects char* mapping)
        """
        # Check for va_list types (platform-specific variadic argument list)
        # These appear as __va_list_tag or __builtin_va_list and cannot be mapped to C#
        if hasattr(ctype, 'spelling'):
            type_spelling = ctype.spelling
            if type_spelling and ('__va_list' in type_spelling or type_spelling == 'va_list'):
                return None  # Signal that this type cannot be mapped
        
        # Handle constant arrays - these need special syntax in C#
        # For now, we'll skip them as they often appear with va_list
        if ctype.kind == TypeKind.CONSTANTARRAY:
            element_type = ctype.get_array_element_type()
            # Check if it's a va_list array
            if hasattr(element_type, 'spelling'):
                element_spelling = element_type.spelling
                if element_spelling and ('__va_list' in element_spelling or element_spelling == 'va_list'):
                    return None  # Cannot map va_list
            # For other arrays, we'd need to use fixed buffers or unsafe arrays
            # For now, return None to skip these
            return None
        
        # Handle pointers
        if ctype.kind == TypeKind.POINTER:
            pointee = ctype.get_pointee()
            
            # char* handling depends on context:
            # - Return type: nuint (caller shouldn't free the pointer)
            # - Parameter: string (for passing C strings as input)
            if pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U):
                return "nuint" if is_return_type else "string"
            
            # void* -> nint
            if pointee.kind == TypeKind.VOID:
                return "nint"
            
            # Check for opaque types (works for both RECORD and ELABORATED types)
            struct_name = None
            if pointee.kind == TypeKind.ELABORATED:
                # For elaborated types, use the spelling directly
                struct_name = pointee.spelling if hasattr(pointee, 'spelling') else None
            elif pointee.kind == TypeKind.RECORD:
                # For record types, strip 'struct ' prefix
                if hasattr(pointee, 'spelling'):
                    struct_name = pointee.spelling
                    for prefix in ['struct ', 'union ', 'class ']:
                        if struct_name.startswith(prefix):
                            struct_name = struct_name[len(prefix):]
                            break
            
            # If it's an opaque type, use unsafe pointer
            if struct_name and struct_name in self.opaque_types:
                return f"{struct_name}*"
            
            # Pointer to struct -> nint (for non-opaque structs)
            if pointee.kind in (TypeKind.RECORD, TypeKind.ELABORATED):
                return "nint"
            
            # Other pointers -> nint for safety
            return "nint"
        
        # Basic types
        if ctype.kind in self.type_map:
            return self.type_map[ctype.kind]
        
        # Handle elaborated types (e.g., 'struct Foo' vs 'Foo')
        if ctype.kind == TypeKind.ELABORATED:
            # Check if the spelling is a known typedef
            if hasattr(ctype, 'spelling'):
                spelling = ctype.spelling
                if spelling and spelling in self.typedef_map:
                    return self.typedef_map[spelling]
            else:
                spelling = None
            # Get the named type and map it
            named_type = ctype.get_named_type()
            if named_type.kind != TypeKind.INVALID:
                return self.map_type(named_type)
            # Fallback: strip 'struct ', 'enum ', 'union ' prefixes
            if spelling:
                for prefix in ['struct ', 'enum ', 'union ', 'class ']:
                    if spelling.startswith(prefix):
                        return spelling[len(prefix):]
            return spelling if spelling else "nint"
        
        # Typedef - check common typedefs first
        if ctype.kind == TypeKind.TYPEDEF:
            if hasattr(ctype, 'spelling'):
                typedef_name = ctype.spelling
                if typedef_name and typedef_name in self.typedef_map:
                    return self.typedef_map[typedef_name]
            # Otherwise resolve to canonical type
            return self.map_type(ctype.get_canonical())
        
        # Enum - strip 'enum ' prefix
        if ctype.kind == TypeKind.ENUM:
            spelling = ctype.spelling if hasattr(ctype, 'spelling') else None
            if not spelling:
                spelling = "int"
            if spelling.startswith('enum '):
                return spelling[5:]  # Strip 'enum ' prefix
            return spelling
        
        # Struct/Union - strip any 'struct'/'union' prefix
        if ctype.kind == TypeKind.RECORD:
            if hasattr(ctype, 'spelling'):
                spelling = ctype.spelling
                if spelling:
                    for prefix in ['struct ', 'union ', 'class ']:
                        if spelling.startswith(prefix):
                            return spelling[len(prefix):]
                    return spelling
            return "nint"
        
        # Fallback
        return ctype.spelling if hasattr(ctype, 'spelling') and ctype.spelling else "nint"
