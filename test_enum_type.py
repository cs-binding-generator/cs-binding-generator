#!/usr/bin/env python3
"""Test script to explore enum underlying types with libclang"""

from clang.cindex import Index, TranslationUnit, CursorKind
import tempfile
import os

# Create a test C header with various enum types
test_code = """
enum PlainEnum {
    PLAIN_A = 0,
    PLAIN_B = 1
};

enum : int {
    ANON_INT_A = 10,
    ANON_INT_B = 11
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

typedef enum {
    TYPEDEF_A = 50,
    TYPEDEF_B = 51
} TypedefEnum;
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
            print(f"{indent}  Type: {cursor.type}")
            print(f"{indent}  Type kind: {cursor.type.kind}")
            print(f"{indent}  Type spelling: {cursor.type.spelling}")
            
            # Try to get underlying type
            if hasattr(cursor.type, 'get_canonical'):
                canonical = cursor.type.get_canonical()
                print(f"{indent}  Canonical type: {canonical}")
                print(f"{indent}  Canonical kind: {canonical.kind}")
                print(f"{indent}  Canonical spelling: {canonical.spelling}")
            
            # Check if enum has underlying type specification
            if hasattr(cursor, 'enum_type'):
                print(f"{indent}  Enum underlying type: {cursor.enum_type}")
            
            # Alternative ways to get underlying type
            try:
                underlying = cursor.type.get_canonical()
                print(f"{indent}  Underlying type via canonical: {underlying}")
            except:
                pass
                
            # Explore enum members
            for child in cursor.get_children():
                if child.kind == CursorKind.ENUM_CONSTANT_DECL:
                    print(f"{indent}    Member: {child.spelling} = {child.enum_value}")
            print()
        
        # Recurse into children
        for child in cursor.get_children():
            explore_enum(child, depth + 1)
    
    # Start exploration from root
    print("Exploring enum declarations:")
    explore_enum(translation_unit.cursor)
    
finally:
    # Clean up
    os.unlink(temp_file)
