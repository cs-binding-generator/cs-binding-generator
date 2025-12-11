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
    
    def map_type(self, ctype) -> str:
        """Map C type to C# type"""
        # Handle pointers
        if ctype.kind == TypeKind.POINTER:
            pointee = ctype.get_pointee()
            
            # char* -> string (for C strings)
            if pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U):
                return "string"
            
            # void* -> nint
            if pointee.kind == TypeKind.VOID:
                return "nint"
            
            # Pointer to struct -> nint
            if pointee.kind == TypeKind.RECORD:
                return "nint"  # Or use ref for by-reference
            
            # Other pointers -> nint for safety
            return "nint"
        
        # Basic types
        if ctype.kind in self.type_map:
            return self.type_map[ctype.kind]
        
        # Handle elaborated types (e.g., 'struct Foo' vs 'Foo')
        if ctype.kind == TypeKind.ELABORATED:
            # Check if the spelling is a known typedef
            if ctype.spelling in self.typedef_map:
                return self.typedef_map[ctype.spelling]
            # Get the named type and map it
            named_type = ctype.get_named_type()
            if named_type.kind != TypeKind.INVALID:
                return self.map_type(named_type)
            # Fallback: strip 'struct ', 'enum ', 'union ' prefixes
            spelling = ctype.spelling
            for prefix in ['struct ', 'enum ', 'union ', 'class ']:
                if spelling.startswith(prefix):
                    return spelling[len(prefix):]
            return spelling if spelling else "nint"
        
        # Typedef - check common typedefs first
        if ctype.kind == TypeKind.TYPEDEF:
            typedef_name = ctype.spelling
            if typedef_name in self.typedef_map:
                return self.typedef_map[typedef_name]
            # Otherwise resolve to canonical type
            return self.map_type(ctype.get_canonical())
        
        # Enum
        if ctype.kind == TypeKind.ENUM:
            return ctype.spelling or "int"
        
        # Struct/Union - strip any 'struct'/'union' prefix
        if ctype.kind == TypeKind.RECORD:
            spelling = ctype.spelling
            for prefix in ['struct ', 'union ', 'class ']:
                if spelling.startswith(prefix):
                    return spelling[len(prefix):]
            return spelling
        
        # Fallback
        return ctype.spelling or "nint"
