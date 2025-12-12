#!/usr/bin/env python3
"""Test enum inheritance feature"""

import tempfile
import os
from cs_binding_generator.generator import CSharpBindingsGenerator

def test_enum_inheritance():
    """Test that enum inheritance is properly generated"""
    
    # Create test header with various enum types
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

enum ByteEnum : unsigned char {
    BYTE_A = 40,
    BYTE_B = 41
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
        # Generate bindings
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(temp_file, "testlib")],
            namespace="TestEnums"
        )
        
        print("Generated C# code:")
        print(result)
        
        # Check that inheritance is correctly applied
        assert "public enum ByteEnum : byte" in result
        assert "public enum IntEnum\n{" in result  # No inheritance for int (default)
        assert "public enum PlainEnum : uint" in result  # PlainEnum gets uint underlying type
        assert "public enum ShortEnum : short" in result
        assert "public enum UIntEnum : uint" in result
        assert "public enum LongEnum : long" in result
        
        print("✅ All enum inheritance tests passed!")
        
    finally:
        # Clean up
        os.unlink(temp_file)

if __name__ == "__main__":
    test_enum_inheritance()