"""
Type mapping logic for converting C types to C# types
"""

from clang.cindex import TypeKind
from .constants import CSHARP_TYPE_MAP


class TypeMapper:
    """Maps C/libclang types to C# types"""
    
    def __init__(self):
        self.type_map = CSHARP_TYPE_MAP.copy()
    
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
        
        # Typedef - get the canonical type
        if ctype.kind == TypeKind.TYPEDEF:
            return self.map_type(ctype.get_canonical())
        
        # Enum
        if ctype.kind == TypeKind.ENUM:
            return ctype.spelling or "int"
        
        # Struct/Union
        if ctype.kind == TypeKind.RECORD:
            return ctype.spelling
        
        # Fallback
        return ctype.spelling or "nint"
