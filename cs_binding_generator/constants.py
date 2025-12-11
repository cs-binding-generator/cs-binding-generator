"""
Constants and mappings for C# bindings generation
"""

from clang.cindex import TypeKind


# Mapping from C/libclang types to C# types
CSHARP_TYPE_MAP = {
    TypeKind.VOID: "void",
    TypeKind.BOOL: "bool",
    TypeKind.CHAR_S: "sbyte",
    TypeKind.CHAR_U: "byte",
    TypeKind.UCHAR: "byte",
    TypeKind.SCHAR: "sbyte",
    TypeKind.SHORT: "short",
    TypeKind.USHORT: "ushort",
    TypeKind.INT: "int",
    TypeKind.UINT: "uint",
    TypeKind.LONG: "int",
    TypeKind.ULONG: "uint",
    TypeKind.LONGLONG: "long",
    TypeKind.ULONGLONG: "ulong",
    TypeKind.FLOAT: "float",
    TypeKind.DOUBLE: "double",
    TypeKind.LONGDOUBLE: "double",  # C# doesn't have long double, use double (may lose precision)
    TypeKind.POINTER: "nint",  # Generic pointer, refined in type_mapper
}

# C# usings required for generated code
REQUIRED_USINGS = [
    "using System.Runtime.InteropServices;",
    "using System.Runtime.InteropServices.Marshalling;",
    "using System.Runtime.CompilerServices;",
]

# Default namespace for generated bindings
DEFAULT_NAMESPACE = "Bindings"

# Default class name for native methods
NATIVE_METHODS_CLASS = "NativeMethods"
