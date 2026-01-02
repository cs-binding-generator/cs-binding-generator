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
            "size_t": "nuint",
            "ssize_t": "nint",
            "ptrdiff_t": "nint",
            "intptr_t": "nint",
            "uintptr_t": "nuint",
            "wchar_t": "char",
        }
        # Track opaque types (empty structs used as handles)
        self.opaque_types = set()
        # Global renames that apply to all types/functions - list of (pattern, replacement, is_regex) tuples
        self.renames = []
        # Global removals that filter out types/functions - list of (pattern, is_regex) tuples
        self.removals = []
        # Global flag enums that should have [Flags] attribute - list of (pattern, is_regex) tuples
        self.flag_enums = []

    def register_typedef(self, name: str, underlying_type) -> None:
        """Register a typedef for later resolution"""
        if name not in self.typedef_chain:
            self.typedef_chain[name] = underlying_type

    def resolve_typedef_chain(self, type_name: str) -> str | None:
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

            # If canonical is a primitive type, map it (use size-aware mapping)
            if canonical.kind in self.type_map:
                return self._map_primitive_kind(canonical.kind, canonical)

            # If it's a struct/union, get the name from canonical
            if canonical.kind == TypeKind.RECORD:
                resolved_name = canonical.spelling
                # Strip struct/union prefix
                for prefix in ["struct ", "union ", "class "]:
                    if resolved_name.startswith(prefix):
                        resolved_name = resolved_name[len(prefix) :]
                        break
                # Check if this name is also a typedef
                if resolved_name in self.typedef_chain and resolved_name != current_name:
                    current_name = resolved_name
                    continue
                else:
                    return str(resolved_name)

            # If it's another typedef, continue the chain
            if underlying.spelling and underlying.spelling != current_name:
                next_name = underlying.spelling
                # Strip qualifiers
                for prefix in ["const ", "struct ", "union ", "enum "]:
                    if next_name.startswith(prefix):
                        next_name = next_name[len(prefix) :]
                        break
                if next_name in self.typedef_chain:
                    current_name = next_name
                else:
                    return str(next_name)
            else:
                break

        return None

    def map_type(self, ctype, is_return_type: bool = False, is_struct_field: bool = False) -> str | None:
        """Map C type to C# type

        Args:
            ctype: The libclang type to map
            is_return_type: True if this is a function return type (affects char* mapping)
            is_struct_field: True if this is a struct field (affects char* mapping)
        """
        # Check for va_list types (platform-specific variadic argument list)
        # These appear as __va_list_tag or __builtin_va_list and cannot be mapped to C#
        if hasattr(ctype, "spelling"):
            type_spelling = ctype.spelling
            # Defensive: ensure we treat non-string spellings safely (mocks may provide Mock)
            try:
                type_spelling_str = str(type_spelling) if type_spelling is not None else ""
            except Exception:
                type_spelling_str = ""
            if type_spelling_str and ("__va_list" in type_spelling_str or type_spelling_str == "va_list"):
                return None  # Signal that this type cannot be mapped

        # Handle constant arrays - these need special syntax in C#
        # For now, we'll skip them as they often appear with va_list
        if ctype.kind == TypeKind.CONSTANTARRAY:
            element_type = ctype.get_array_element_type()
            # Check if it's a va_list array
            if hasattr(element_type, "spelling"):
                element_spelling = element_type.spelling
                if element_spelling and ("__va_list" in element_spelling or element_spelling == "va_list"):
                    return None  # Cannot map va_list
            # For other arrays, we'd need to use fixed buffers or unsafe arrays
            # For now, return None to skip these
            return None

        # Handle incomplete arrays (e.g., const char* const items[])
        # These appear as function parameters and should be treated as pointers
        if ctype.kind == TypeKind.INCOMPLETEARRAY:
            element_type = ctype.get_array_element_type()
            # Map the element type
            element_mapped = self.map_type(element_type, is_return_type=False, is_struct_field=False)
            if element_mapped is None:
                return None
            # Incomplete array of pointers becomes pointer-to-pointer
            # e.g., const char*[] -> nuint* or byte**
            if element_type.kind == TypeKind.POINTER:
                # For char* arrays, use nuint (not byte**)
                pointee = element_type.get_pointee()
                if pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U):
                    return "nuint"
                # For other pointer arrays, return pointer to the mapped element type
                return f"{element_mapped}*"
            # For non-pointer element types, return pointer to the element type
            return f"{element_mapped}*"

        # Handle pointers
        if ctype.kind == TypeKind.POINTER:
            pointee = ctype.get_pointee()

            # char* handling depends on context:
            # - Return type: nuint (caller shouldn't free the pointer)
            # - Struct field: nuint (must be unmanaged)
            # - Parameter: string (for passing C strings as input)
            if pointee.kind in (TypeKind.CHAR_S, TypeKind.CHAR_U):
                # Return types and struct fields should remain unmanaged (`nuint`),
                # but parameters that accept strings should be nullable (`string?`) to
                # reflect that C APIs often accept NULL for optional strings.
                return "nuint" if (is_return_type or is_struct_field) else "string?"

            # void* -> nint
            if pointee.kind == TypeKind.VOID:
                return "nint"

            # Handle pointer to typedef (e.g., Uint8*, Sint16*)
            # ELABORATED types can also be typedefs - check typedef chain first
            pointee_name = pointee.spelling if hasattr(pointee, "spelling") else None

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
                for prefix in ["const ", "volatile ", "restrict "]:
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
                if hasattr(pointee, "spelling"):
                    struct_name = pointee.spelling
                    # Strip const and other qualifiers - may need multiple passes
                    while True:
                        stripped = False
                        for prefix in ["const ", "volatile ", "restrict ", "struct ", "union ", "enum ", "class "]:
                            if struct_name.startswith(prefix):
                                struct_name = struct_name[len(prefix) :]
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
                if hasattr(pointee, "spelling"):
                    struct_name = pointee.spelling
                    while True:
                        stripped = False
                        for prefix in ["const ", "volatile ", "struct ", "union ", "class "]:
                            if struct_name.startswith(prefix):
                                struct_name = struct_name[len(prefix) :]
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
 
            # Function pointer (pointer to function prototype) -> when used as a struct field
            # libclang represents function pointers as POINTER whose pointee is FUNCTIONPROTO/FUNCTIONNOPROTO
            # Emit a raw C# function pointer type for struct fields so it can be cast/invoked by consumers.
            # Use unmanaged Cdecl calling convention as a sensible default for C libraries.
            if pointee.kind in (TypeKind.FUNCTIONPROTO, TypeKind.FUNCTIONNOPROTO):
                # Try to build an accurate C# function-pointer signature.
                # Default to using nint for unknown return/parameter types.
                try:
                    # Determine return type
                    ret_type = None
                    if hasattr(pointee, "get_result"):
                        ret = pointee.get_result()
                        if ret:
                            mapped_ret = self.map_type(ret, is_return_type=True)
                            ret_type = mapped_ret or "nint"
                    elif hasattr(pointee, "result_type"):
                        # Some mocks or libclang variants expose result_type
                        ret = getattr(pointee, "result_type")
                        mapped_ret = self.map_type(ret, is_return_type=True) if ret else None
                        ret_type = mapped_ret or "nint"
                    else:
                        ret_type = "nint"

                    # Determine parameter types
                    param_types: list[str] = []
                    # libclang Type may expose an argument iterator via 'argument_types' or 'get_arguments'
                    if hasattr(pointee, "argument_types") and callable(pointee.argument_types):
                        try:
                            for a in pointee.argument_types():
                                mapped = self.map_type(a, is_return_type=False)
                                param_types.append(mapped or "nint")
                        except Exception:
                            param_types = []
                    elif hasattr(pointee, "get_arg_types") and callable(pointee.get_arg_types):
                        try:
                            for a in pointee.get_arg_types():
                                mapped = self.map_type(a, is_return_type=False)
                                param_types.append(mapped or "nint")
                        except Exception:
                            param_types = []
                    elif hasattr(pointee, "arg_types"):
                        try:
                            for a in getattr(pointee, "arg_types"):
                                mapped = self.map_type(a, is_return_type=False)
                                param_types.append(mapped or "nint")
                        except Exception:
                            param_types = []

                    # Filter out 'void' parameters which indicate no parameters
                    param_types = [p for p in param_types if p and p != "void"]

                    # Fallback when we couldn't discover parameters
                    if not param_types:
                        # Emit signature with just the return type (no parameters)
                        sig = f"delegate* unmanaged[Cdecl]<{ret_type}>"
                    else:
                        # C# function-pointer generic list expects parameter types first, return type last
                        sig = f"delegate* unmanaged[Cdecl]<{', '.join(param_types + [ret_type])}>"

                    return sig
                except Exception:
                    return "delegate* unmanaged[Cdecl]<nint>"
            
            # Handle pointers to enums (e.g., MyEnum* -> MyEnum*, not "enum MyEnum*")
            if pointee.kind == TypeKind.ENUM:
                enum_name = pointee.spelling if hasattr(pointee, "spelling") else None
                if enum_name:
                    # Strip "enum " prefix if present
                    if enum_name.startswith("enum "):
                        enum_name = enum_name[5:]
                    # Apply any renames and return as typed pointer
                    return f"{self.apply_rename(enum_name)}*"
                # Fallback for unnamed enums
                return "int*"
            
            # Handle pointers to primitive types (e.g., int*, uint*, float*)
            # This must come before the nint fallback
            if pointee.kind in self.type_map:
                primitive_type = self._map_primitive_kind(pointee.kind, pointee, is_struct_field=False)
                return f"{primitive_type}*"
            
            # Other pointers -> nint for safety
            return "nint"

        # Basic types (use size-aware mapping for some kinds)
        if ctype.kind in self.type_map:
            return self._map_primitive_kind(ctype.kind, ctype, is_struct_field)

        # Handle elaborated types (e.g., 'struct Foo' vs 'Foo')
        if ctype.kind == TypeKind.ELABORATED:
            # Check if this is a typedef for a pointer or function pointer type
            # (common opaque pointer pattern: typedef struct X *Y;)
            canonical = ctype.get_canonical()
            if canonical.kind in (TypeKind.POINTER, TypeKind.FUNCTIONPROTO, TypeKind.FUNCTIONNOPROTO):
                return "nint"

            # Try to resolve through typedef chain first
            if hasattr(ctype, "spelling") and ctype.spelling:
                resolved = self.resolve_typedef_chain(ctype.spelling)
                if resolved:
                    return self.apply_rename(resolved)

            # For non-pointer typedefs, try to resolve to canonical primitive type
            if canonical.kind != ctype.kind:  # If canonical is different from original
                if canonical.kind in self.type_map:
                    return str(self.type_map[canonical.kind])
                # Recursively map the canonical type
                mapped_canonical = self.map_type(canonical, is_return_type, is_struct_field)
                # If the canonical type returns a clean struct name, use it
                if mapped_canonical and mapped_canonical != "nint":
                    return str(mapped_canonical)

            # Check if the spelling is a known typedef
            if hasattr(ctype, "spelling"):
                spelling = ctype.spelling
                # Strip qualifiers before checking typedef_map
                clean_spelling = spelling
                for prefix in ["const ", "volatile ", "restrict ", "struct ", "union ", "enum ", "class "]:
                    while clean_spelling.startswith(prefix):
                        clean_spelling = clean_spelling[len(prefix) :]

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
                for prefix in ["struct ", "enum ", "union ", "class "]:
                    if spelling.startswith(prefix):
                        return str(self.apply_rename(spelling[len(prefix) :]))
            return str(self.apply_rename(spelling)) if spelling else "nint"

        # Typedef - check typedef chain first, then common typedefs
        if ctype.kind == TypeKind.TYPEDEF:
            if hasattr(ctype, "spelling"):
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
            spelling = ctype.spelling if hasattr(ctype, "spelling") else None
            if not spelling:
                spelling = "int"
            if spelling.startswith("enum "):
                spelling = spelling[5:]  # Strip 'enum ' prefix
            return self.apply_rename(spelling)

        # Struct/Union - strip any 'struct'/'union'/'const' prefix
        if ctype.kind == TypeKind.RECORD:
            if hasattr(ctype, "spelling"):
                spelling = ctype.spelling
                if spelling:
                    # Strip all qualifiers and keywords
                    changed = True
                    while changed:
                        changed = False
                        for prefix in ["const ", "volatile ", "restrict ", "struct ", "union ", "class "]:
                            if spelling.startswith(prefix):
                                spelling = spelling[len(prefix) :]
                                changed = True
                                break
                    return self.apply_rename(spelling) if spelling else "nint"
            return "nint"

        # Fallback
        spelling = ctype.spelling if hasattr(ctype, "spelling") and ctype.spelling else None
        if spelling:
            # Strip ALL qualifiers and keywords repeatedly
            changed = True
            while changed:
                changed = False
                for prefix in ["const ", "volatile ", "restrict ", "struct ", "union ", "enum ", "class "]:
                    if spelling.startswith(prefix):
                        spelling = spelling[len(prefix) :]
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
                    replacement_py = replacement.replace("$", "\\")
                    result = re.sub(pattern, replacement_py, result)
                    break  # First match wins
            else:
                # Simple exact match
                if result == pattern:
                    result = replacement
                    break  # First match wins
        return result

    def get_all_renames(self) -> list[tuple[str, str, bool]]:
        """Get all rename mappings as list of tuples"""
        return list(self.renames)

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

    def get_all_removals(self) -> list[tuple[str, bool]]:
        """Get all removal patterns as list of tuples"""
        return list(self.removals)

    def add_flag_enum(self, pattern: str, is_regex: bool = False):
        """Add a flag enum pattern to mark enums with [Flags] attribute"""
        self.flag_enums.append((pattern, is_regex))

    def is_flag_enum(self, name: str) -> bool:
        """Check if an enum should have [Flags] attribute (first match wins)"""
        import re

        for pattern, is_regex in self.flag_enums:
            if is_regex:
                # Use fullmatch for precise identifier matching
                if re.fullmatch(pattern, name):
                    return True  # First match wins
            else:
                # Simple exact match
                if name == pattern:
                    return True  # First match wins
        return False

    def _map_primitive_kind(self, kind, ctype, is_struct_field: bool = False) -> str:
        """Map primitive TypeKind to C# type, considering platform-sized types like long/unsigned long

        `ctype` may provide size information via `get_size()` which returns size in bytes when available.
        Use that to decide whether C `long` maps to C# `int` (32-bit) or `long` (64-bit).
        
        For struct fields, `bool` is mapped to `byte` to avoid managed type issues in unmanaged structs.
        """
        from clang.cindex import TypeKind

        # Map bool to byte in struct fields to ensure unmanaged structs
        if kind == TypeKind.BOOL and is_struct_field:
            return "byte"

        # Handle long/unsigned long specially based on size
        if kind == TypeKind.LONG:
            try:
                size = ctype.get_size()
                # If size is 8 bytes, map to C# long, otherwise map to int
                return "long" if size == 8 else "int"
            except Exception:
                return "int"
        if kind == TypeKind.ULONG:
            try:
                size = ctype.get_size()
                return "ulong" if size == 8 else "uint"
            except Exception:
                return "uint"

        # Default mapping from the constants table
        return str(self.type_map.get(kind, "nint"))
