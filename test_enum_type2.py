#!/usr/bin/env python3
"""Test script to explore enum underlying types with libclang"""

from clang.cindex import Index, TranslationUnit, CursorKind, TypeKind
import tempfile
import os

# Create a test C header with various enum types
test_code = """
enum PlainEnum {
    PLAIN_A = 0,
    PLAIN_B = 1
};

enum IntEnum : int {
    INT_A = 20,
    INT_B = 21
};

enum ShortEnum : short {
    SHORT_A = 30,
    SHORT_B = 31
};

enum UCharEnum : unsigned char {
    UCHAR_A = 40,
    UCHAR_B = 41
};

enum UIntEnum : unsigned int {
    UINT_A = 50,
    UINT_B = 51
};

enum LongEnum : long {
    LONG_A = 60,
    LONG_B = 61
};
"""

# Write test code to temporary file
with tempfile.NamedTemporaryFile(mode='w', suffix='.h', delete=False) as f:
    f.write(test_code)
    temp_file = f.name

try:
    # Parse with libclang
    index = Index.create()
    translation_unit = index.parse(temp_file)
    
    def explore_enum(cursor, depth=0):
        """Recursively explore cursor looking for enums"""
        indent = "  " * depth
        
        if cursor.kind == CursorKind.ENUM_DECL:
            print(f"{indent}ENUM: {cursor.spelling or '<anonymous>'}")
            
            # Get underlying type
            if hasattr(cursor, 'enum_type'):
                underlying_type = cursor.enum_type
                print(f"{indent}  Underlying type: {underlying_type}")
                print(f"{indent}  Underlying kind: {underlying_type.kind}")
                print(f"{indent}  Underlying spelling: {underlying_type.spelling}")
                
                # Map to C# types
                csharp_map = {
                    TypeKind.INT: "int",
                    TypeKind.UINT: "uint", 
                    TypeKind.SHORT: "short",
                    TypeKind.USHORT: "ushort",
                    TypeKind.CHAR_S: "sbyte",
                    TypeKind.CHAR_U: "byte",
                    TypeKind.UCHAR: "byte",
                    TypeKind.SCHAR: "sbyte",
                    TypeKind.LONG: "long",
                    TypeKind.ULONG: "ulong",
                    TypeKind.LONGLONG: "long",
                    TypeKind.ULONGLONG: "ulong"
                }
                
                csharp_type = csharp_map.get(underlying_type.kind, "int")
                print(f"{indent}  C# type: {csharp_type}")
                
            print()
        
        # Recurse into children
        for child in cursor.get_children():
            explore_enum(child, depth + 1)
    
    # Start exploration from root
    print("Exploring enum declarations and their underlying types:")
    explore_enum(translation_unit.cursor)
    
finally:
    # Clean up
    os.unlink(temp_file)
