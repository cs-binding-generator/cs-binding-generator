"""
Unit tests for TypeMapper
"""

import pytest
from unittest.mock import Mock
from clang.cindex import TypeKind

from cs_binding_generator.type_mapper import TypeMapper


class TestTypeMapper:
    """Test the TypeMapper class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mapper = TypeMapper()
    
    def test_basic_types(self):
        """Test mapping of basic C types to C# types"""
        test_cases = [
            (TypeKind.VOID, "void"),
            (TypeKind.BOOL, "bool"),
            (TypeKind.INT, "int"),
            (TypeKind.UINT, "uint"),
            (TypeKind.FLOAT, "float"),
            (TypeKind.DOUBLE, "double"),
            (TypeKind.SHORT, "short"),
            (TypeKind.USHORT, "ushort"),
            (TypeKind.LONG, "int"),
            (TypeKind.ULONG, "uint"),
            (TypeKind.LONGLONG, "long"),
            (TypeKind.ULONGLONG, "ulong"),
        ]
        
        for c_type_kind, expected_csharp in test_cases:
            mock_type = Mock()
            mock_type.kind = c_type_kind
            mock_type.spelling = ""
            
            result = self.mapper.map_type(mock_type)
            assert result == expected_csharp, f"Expected {expected_csharp} for {c_type_kind}, got {result}"
    
    def test_char_types(self):
        """Test mapping of char types"""
        test_cases = [
            (TypeKind.CHAR_S, "sbyte"),
            (TypeKind.CHAR_U, "byte"),
            (TypeKind.UCHAR, "byte"),
            (TypeKind.SCHAR, "sbyte"),
        ]
        
        for c_type_kind, expected_csharp in test_cases:
            mock_type = Mock()
            mock_type.kind = c_type_kind
            mock_type.spelling = ""
            
            result = self.mapper.map_type(mock_type)
            assert result == expected_csharp
    
    def test_void_pointer(self):
        """Test that void* maps to nint"""
        mock_type = Mock()
        mock_type.kind = TypeKind.POINTER
        mock_type.spelling = "void *"
        
        mock_pointee = Mock()
        mock_pointee.kind = TypeKind.VOID
        mock_pointee.spelling = "void"
        mock_type.get_pointee.return_value = mock_pointee
        
        result = self.mapper.map_type(mock_type)
        assert result == "nint"
    
    def test_char_pointer_to_string(self):
        """Test that char* maps to string"""
        for char_kind in [TypeKind.CHAR_S, TypeKind.CHAR_U]:
            mock_type = Mock()
            mock_type.kind = TypeKind.POINTER
            mock_type.spelling = "char *"
            
            mock_pointee = Mock()
            mock_pointee.kind = char_kind
            mock_pointee.spelling = "char"
            mock_type.get_pointee.return_value = mock_pointee
            
            result = self.mapper.map_type(mock_type)
            assert result == "string"
    
    def test_struct_pointer(self):
        """Test that struct* maps to Type* (typed pointer)"""
        mock_type = Mock()
        mock_type.kind = TypeKind.POINTER
        mock_type.spelling = "struct Point *"
        
        mock_pointee = Mock()
        mock_pointee.kind = TypeKind.RECORD
        mock_pointee.spelling = "struct Point"
        mock_type.get_pointee.return_value = mock_pointee
        
        result = self.mapper.map_type(mock_type)
        assert result == "Point*"
    
    def test_opaque_struct_pointer(self):
        """Test that opaque struct* maps to Type*"""
        # Register SDL_Window as an opaque type
        self.mapper.opaque_types.add("SDL_Window")
        
        mock_type = Mock()
        mock_type.kind = TypeKind.POINTER
        mock_type.spelling = "SDL_Window *"
        
        mock_pointee = Mock()
        mock_pointee.kind = TypeKind.RECORD
        mock_pointee.spelling = "SDL_Window"
        mock_type.get_pointee.return_value = mock_pointee
        
        result = self.mapper.map_type(mock_type)
        assert result == "SDL_Window*"
        
        # Also test with 'struct ' prefix
        mock_pointee.spelling = "struct SDL_Window"
        result = self.mapper.map_type(mock_type)
        assert result == "SDL_Window*"
    
    def test_generic_pointer(self):
        """Test that other pointers map to nint"""
        mock_type = Mock()
        mock_type.kind = TypeKind.POINTER
        mock_type.spelling = "int *"
        
        mock_pointee = Mock()
        mock_pointee.kind = TypeKind.INT
        mock_pointee.spelling = "int"
        mock_type.get_pointee.return_value = mock_pointee
        
        result = self.mapper.map_type(mock_type)
        assert result == "nint"
    
    def test_enum_type(self):
        """Test that enums map to their spelling or int"""
        mock_type = Mock()
        mock_type.kind = TypeKind.ENUM
        mock_type.spelling = "MyEnum"
        
        result = self.mapper.map_type(mock_type)
        assert result == "MyEnum"
        
        # Test unnamed enum
        mock_type.spelling = ""
        result = self.mapper.map_type(mock_type)
        assert result == "int"
    
    def test_struct_type(self):
        """Test that structs map to their spelling"""
        mock_type = Mock()
        mock_type.kind = TypeKind.RECORD
        mock_type.spelling = "Point"
        
        result = self.mapper.map_type(mock_type)
        assert result == "Point"
    
    def test_typedef(self):
        """Test that typedefs preserve typedef name (updated behavior)"""
        mock_type = Mock()
        mock_type.kind = TypeKind.TYPEDEF
        mock_type.spelling = "my_int"
        
        mock_canonical = Mock()
        mock_canonical.kind = TypeKind.INT
        mock_canonical.spelling = "int"
        mock_type.get_canonical.return_value = mock_canonical
        
        result = self.mapper.map_type(mock_type)
        assert result == "my_int"
    
    def test_fallback_type(self):
        """Test fallback for unknown types"""
        mock_type = Mock()
        mock_type.kind = TypeKind.UNEXPOSED  # Unknown type
        mock_type.spelling = "UnknownType"
        
        result = self.mapper.map_type(mock_type)
        assert result == "UnknownType"
        
        # Test with empty spelling
        mock_type.spelling = ""
        result = self.mapper.map_type(mock_type)
        assert result == "nint"
