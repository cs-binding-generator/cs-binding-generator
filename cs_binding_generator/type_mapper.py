"""
Type mapping logic for converting C types to C# types
"""

from clang.cindex import TypeKind
from .constants import CSHARP_TYPE_MAP


class TypeMapper:
    """Maps C/libclang types to C# types"""
    
    def __init__(self):
        self.type_map = CSHARP_TYPE_MAP.copy()
        # Typedef resolution map: maps typedef name to underlying clang Type
        self.typedef_chain = {}
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
        # Global renames that apply to all types/functions - list of (pattern, replacement, is_regex) tuples
        self.renames = []
        # Global removals that filter out types/functions - list of (pattern, is_regex) tuples
        self.removals = []
    
    def register_typedef(self, name: str, underlying_type):
        """Register a typedef for later resolution"""
        if name not in self.typedef_chain:
            self.typedef_chain[name] = underlying_type
    
    def resolve_typedef_chain(self, type_name: str):
        """Resolve a typedef to its final underlying type"""
        visited = set()
        current_name = type_name
        
        # Follow the chain of typedefs
        while current_name in self.typedef_chain:
            if current_name in visited:
                # Circular typedef, shouldn't happen but be safe
                break
            visited.add(current_name)
            
            underlying = self.typedef_chain[current_name]
            # Get the canonical type to resolve through typedefs
            canonical = underlying.get_canonical()
            
            # If canonical is a primitive type, map it
            if canonical.kind in self.type_map:
                return self.type_map[canonical.kind]
            
            # If it's a struct/union, get the name from canonical
            if canonical.kind == TypeKind.RECORD:
                resolved_name = canonical.spelling
                # Strip struct/union prefix
                for prefix in ['struct ', 'union ', 'class ']:
                    if resolved_name.startswith(prefix):
                        resolved_name = resolved_name[len(prefix):]
                        break
                # Check if this name is also a typedef
                if resolved_name in self.typedef_chain and resolved_name != current_name:
                    current_name = resolved_name
                    continue
                else:
                    return resolved_name
            
            # If it's another typedef, continue the chain
            if underlying.spelling and underlying.spelling != current_name:
                next_name = underlying.spelling
                # Strip qualifiers
                for prefix in ['const ', 'struct ', 'union ', 'enum ']:
                    if next_name.startswith(prefix):
                        next_name = next_name[len(prefix):]
                        break
                if next_name in self.typedef_chain:
                    current_name = next_name
                else:
                    return next_name
            else:
                break
        
        return None
    
    def map_type(self, ctype, is_return_type: bool = False, is_struct_field: bool = False) -> str:
        """Map C type to C# type
        
        Args:
            ctype: The libclang type to map
            is_return_type: True if this is a function return type (affects char* mapping)
            is_struct_field: True if this is a struct field (affects char* mapping)
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
            # - Struct field: nuint (must be unmanaged)
            # - Parameter: string (for passing C strings as input)
            if pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U):
                return "nuint" if (is_return_type or is_struct_field) else "string"
            
            # void* -> nint
            if pointee.kind == TypeKind.VOID:
                return "nint"
            
            # Handle pointer to typedef (e.g., Uint8*, Sint16*)
            # ELABORATED types can also be typedefs - check typedef chain first
            pointee_name = pointee.spelling if hasattr(pointee, 'spelling') else None
            
            # Handle double pointers (e.g., Uint8** -> byte**, char** -> nuint)
            if pointee.kind == TypeKind.POINTER:
                inner_pointee = pointee.get_pointee()
                # char** should be nuint (not string*) to keep it unmanaged
                if inner_pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U):
                    return "nuint"
                inner_mapped = self.map_type(pointee, is_return_type=False, is_struct_field=is_struct_field)
                if inner_mapped and inner_mapped != "nint":
                    return f"{inner_mapped}*"
            
            # Strip qualifiers from pointee name before checking typedefs
            if pointee_name:
                clean_name = pointee_name
                for prefix in ['const ', 'volatile ', 'restrict ']:
                    clean_name = clean_name.removeprefix(prefix)
                
                # Try typedef chain first (runtime-discovered types)
                resolved = self.resolve_typedef_chain(clean_name)
                if resolved:
                    return f"{self.apply_rename(resolved)}*"
                
                # Fall back to static typedef_map
                if clean_name in self.typedef_map:
                    mapped_type = self.typedef_map[clean_name]
                    # Return the mapped pointer type (including nint* for function pointers)
                    return f"{self.apply_rename(mapped_type)}*"
            
            # Also try mapping if it's explicitly a TYPEDEF kind
            if pointee.kind == TypeKind.TYPEDEF:
                mapped_type = self.map_type(pointee, is_return_type=False)
                if mapped_type and mapped_type != "nint":
                    return f"{mapped_type}*"
            
            # Get struct name for pointer to struct (handles RECORD and ELABORATED types)
            struct_name = None
            if pointee.kind == TypeKind.ELABORATED:
                # For elaborated types, use the spelling directly
                if hasattr(pointee, 'spelling'):
                    struct_name = pointee.spelling
                    # Strip const and other qualifiers - may need multiple passes
                    while True:
                        stripped = False
                        for prefix in ['const ', 'volatile ', 'restrict ', 'struct ', 'union ', 'class ']:
                            if struct_name.startswith(prefix):
                                struct_name = struct_name[len(prefix):]
                                stripped = True
                                break
                        if not stripped:
                            break

                    
                    # Try to resolve through typedef chain for ELABORATED types that are typedefs
                    # Example: SDL_TLSID is ELABORATED but is actually a typedef to SDL_AtomicInt
                    # Note: resolve_typedef_chain returns the underlying C type, apply_rename will be called later
                    resolved = self.resolve_typedef_chain(struct_name)
                    if resolved and resolved != struct_name:
                        struct_name = resolved
            elif pointee.kind == TypeKind.RECORD:
                # For record types, strip 'struct ', 'const ' prefixes - may need multiple passes
                if hasattr(pointee, 'spelling'):
                    struct_name = pointee.spelling
                    while True:
                        stripped = False
                        for prefix in ['const ', 'volatile ', 'struct ', 'union ', 'class ']:
                            if struct_name.startswith(prefix):
                                struct_name = struct_name[len(prefix):]
                                stripped = True
                                break
                        if not stripped:
                            break
            
            # All struct/union pointers use typed pointers (Type*)
            if struct_name:
                return f"{self.apply_rename(struct_name)}*"
            
            # Pointer to struct/union with ELABORATED type but no name
            if pointee.kind in (TypeKind.RECORD, TypeKind.ELABORATED):
                return "nint"
            
            # Other pointers -> nint for safety
            return "nint"
        
        # Basic types
        if ctype.kind in self.type_map:
            return self.type_map[ctype.kind]
        
        # Handle elaborated types (e.g., 'struct Foo' vs 'Foo')
        if ctype.kind == TypeKind.ELABORATED:
            # Check if this is a typedef for a pointer or function pointer type
            # (common opaque pointer pattern: typedef struct X *Y;)
            canonical = ctype.get_canonical()
            if canonical.kind in (TypeKind.POINTER, TypeKind.FUNCTIONPROTO, TypeKind.FUNCTIONNOPROTO):
                return "nint"
            
            # Try to resolve through typedef chain first
            if hasattr(ctype, 'spelling') and ctype.spelling:
                resolved = self.resolve_typedef_chain(ctype.spelling)
                if resolved:
                    return self.apply_rename(resolved)
            
            # For non-pointer typedefs, try to resolve to canonical primitive type
            if canonical.kind != ctype.kind:  # If canonical is different from original
                if canonical.kind in self.type_map:
                    return self.type_map[canonical.kind]
                # Recursively map the canonical type
                mapped_canonical = self.map_type(canonical, is_return_type, is_struct_field)
                # If the canonical type returns a clean struct name, use it
                if mapped_canonical and mapped_canonical != "nint":
                    return mapped_canonical
            
            # Check if the spelling is a known typedef
            if hasattr(ctype, 'spelling'):
                spelling = ctype.spelling
                # Strip qualifiers before checking typedef_map
                clean_spelling = spelling
                for prefix in ['const ', 'volatile ', 'restrict ', 'struct ', 'union ', 'enum ', 'class ']:
                    while clean_spelling.startswith(prefix):
                        clean_spelling = clean_spelling[len(prefix):]
                
                # Try typedef chain first (runtime-discovered types)
                if clean_spelling:
                    resolved = self.resolve_typedef_chain(clean_spelling)
                    if resolved:
                        return resolved
                    
                    # Fall back to static typedef_map
                    if clean_spelling in self.typedef_map:
                        return self.apply_rename(self.typedef_map[clean_spelling])
                
                # If we have a clean spelling after stripping, apply rename and return it
                if clean_spelling:
                    return self.apply_rename(clean_spelling)
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
                        return self.apply_rename(spelling[len(prefix):])
            return self.apply_rename(spelling) if spelling else "nint"
        
        # Typedef - check typedef chain first, then common typedefs
        if ctype.kind == TypeKind.TYPEDEF:
            if hasattr(ctype, 'spelling'):
                typedef_name = ctype.spelling
                if typedef_name:
                    # Try typedef chain first (runtime-discovered types)
                    resolved = self.resolve_typedef_chain(typedef_name)
                    if resolved:
                        return self.apply_rename(resolved)
                    # Fall back to static typedef_map
                    if typedef_name in self.typedef_map:
                        return self.apply_rename(self.typedef_map[typedef_name])
                    # Apply rename to the typedef name itself
                    return self.apply_rename(typedef_name)
            # Otherwise resolve to canonical type
            return self.map_type(ctype.get_canonical())
        
        # Enum - strip 'enum ' prefix and apply renames
        if ctype.kind == TypeKind.ENUM:
            spelling = ctype.spelling if hasattr(ctype, 'spelling') else None
            if not spelling:
                spelling = "int"
            if spelling.startswith('enum '):
                spelling = spelling[5:]  # Strip 'enum ' prefix
            return self.apply_rename(spelling)
        
        # Struct/Union - strip any 'struct'/'union'/'const' prefix
        if ctype.kind == TypeKind.RECORD:
            if hasattr(ctype, 'spelling'):
                spelling = ctype.spelling
                if spelling:
                    # Strip all qualifiers and keywords
                    changed = True
                    while changed:
                        changed = False
                        for prefix in ['const ', 'volatile ', 'restrict ', 'struct ', 'union ', 'class ']:
                            if spelling.startswith(prefix):
                                spelling = spelling[len(prefix):]
                                changed = True
                                break
                    return self.apply_rename(spelling) if spelling else "nint"
            return "nint"
        
        # Fallback
        spelling = ctype.spelling if hasattr(ctype, 'spelling') and ctype.spelling else None
        if spelling:
            # Strip ALL qualifiers and keywords repeatedly
            changed = True
            while changed:
                changed = False
                for prefix in ['const ', 'volatile ', 'restrict ', 'struct ', 'union ', 'enum ', 'class ']:
                    if spelling.startswith(prefix):
                        spelling = spelling[len(prefix):]
                        changed = True
                        break
            return self.apply_rename(spelling) if spelling else "nint"
        return "nint"
    
    def add_rename(self, from_name: str, to_name: str, is_regex: bool = False):
        """Add a global rename mapping"""
        self.renames.append((from_name, to_name, is_regex))
    
    def apply_rename(self, name: str) -> str:
        """Apply rename rules in order (first match wins)"""
        import re
        result = name
        for pattern, replacement, is_regex in self.renames:
            if is_regex:
                # Use fullmatch for precise identifier matching
                if re.fullmatch(pattern, result):
                    # Convert $1, $2 to \1, \2 for Python re.sub
                    replacement_py = replacement.replace('$', '\\')
                    result = re.sub(pattern, replacement_py, result)
                    break  # First match wins
            else:
                # Simple exact match
                if result == pattern:
                    result = replacement
                    break  # First match wins
        return result
    
    def get_all_renames(self) -> list:
        """Get all rename mappings as list of tuples"""
        return self.renames.copy()
    
    def add_removal(self, pattern: str, is_regex: bool = False):
        """Add a removal pattern to filter out types/functions"""
        self.removals.append((pattern, is_regex))
    
    def should_remove(self, name: str) -> bool:
        """Check if a name should be removed (first match wins)"""
        import re
        for pattern, is_regex in self.removals:
            if is_regex:
                # Use fullmatch for precise identifier matching
                if re.fullmatch(pattern, name):
                    return True  # First match wins
            else:
                # Simple exact match
                if name == pattern:
                    return True  # First match wins
        return False
    
    def get_all_removals(self) -> list:
        """Get all removal patterns as list of tuples"""
        return self.removals.copy()
