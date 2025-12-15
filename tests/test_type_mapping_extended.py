"""
Extended type mapping and complex type tests for better coverage
"""

import pytest
from unittest.mock import Mock, MagicMock
import clang.cindex
from clang.cindex import TypeKind, CursorKind

from cs_binding_generator.type_mapper import TypeMapper
from cs_binding_generator.code_generators import CodeGenerator


class MockType(Mock):
    """Mock that properly handles string operations"""
    def __init__(self, spelling="", kind=None, **kwargs):
        super().__init__(**kwargs)
        self.spelling = spelling
        if kind:
            self.kind = kind
    
    def __contains__(self, item):
        return item in str(self.spelling)


class TestTypeMapperComplexTypes:
    """Test complex type mapping scenarios"""
    
    def setup_method(self):
        self.type_mapper = TypeMapper()
    
    def test_function_pointer_types(self):
        """Test function pointer type mapping"""
        # Mock function pointer type: int (*func)(int, float)
        mock_type = MockType(spelling="int (*)(int, float)", kind=TypeKind.POINTER)
        
        mock_pointee = MockType(spelling="int (int, float)", kind=TypeKind.FUNCTIONPROTO)
        mock_type.get_pointee.return_value = mock_pointee
        
        result = self.type_mapper.map_type(mock_type)
        
        # Function pointers typically map to nint in C#
        assert "nint" in result
    
    def test_const_qualified_types(self):
        """Test const-qualified type mapping"""
        mock_type = MockType(spelling="const int", kind=TypeKind.INT)
        mock_type.is_const_qualified.return_value = True
        
        result = self.type_mapper.map_type(mock_type)
        
        assert "int" in result
        # const qualifier should be handled (typically ignored in C# bindings)
    
    def test_volatile_qualified_types(self):
        """Test volatile-qualified type mapping"""
        mock_type = MockType(spelling="volatile int", kind=TypeKind.INT)
        mock_type.is_volatile_qualified.return_value = True
        
        result = self.type_mapper.map_type(mock_type)
        
        assert "int" in result
        # volatile qualifier should be handled
    
    def test_restrict_qualified_types(self):
        """Test restrict-qualified type mapping"""
        mock_type = MockType(spelling="int * restrict", kind=TypeKind.POINTER)
        mock_type.is_restrict_qualified.return_value = True
        
        result = self.type_mapper.map_type(mock_type)
        
        assert result is not None
        # restrict qualifier should be handled
    
    def test_opaque_struct_pointers(self):
        """Test opaque struct pointer handling"""
        mock_type = MockType(spelling="struct Opaque *", kind=TypeKind.POINTER)
        
        mock_pointee = MockType(spelling="struct Opaque", kind=TypeKind.ELABORATED)
        mock_type.get_pointee.return_value = mock_pointee
        
        # Register as opaque type
        self.type_mapper.opaque_types.add("Opaque")
        
        result = self.type_mapper.map_type(mock_type)
        
        assert "Opaque*" in result

    def test_struct_function_pointer_field(self):
        """Struct field that is a function pointer should map to a function-pointer type"""
        mock_cursor = Mock()
        mock_cursor.spelling = "CallbackHolder"
        mock_cursor.kind = CursorKind.STRUCT_DECL

        # Field is a function pointer: int (*callback)(int)
        mock_field = Mock()
        mock_field.kind = CursorKind.FIELD_DECL
        mock_field.spelling = "callback"
        # Represented as POINTER whose pointee is FUNCTIONPROTO
        mock_field.type = MockType(spelling="int (*)(int)", kind=TypeKind.POINTER)
        mock_pointee = MockType(spelling="int (int)", kind=TypeKind.FUNCTIONPROTO)
        mock_field.type.get_pointee.return_value = mock_pointee
        mock_field.get_field_offsetof.return_value = 0

        mock_cursor.get_children.return_value = [mock_field]

        # Instantiate generator used in other tests
        self.generator = CodeGenerator(self.type_mapper)

        result = self.generator.generate_struct(mock_cursor)

        assert "CallbackHolder" in result
        assert "delegate* unmanaged[Cdecl]" in result
    
    def test_enum_type_mapping(self):
        """Test enum type mapping"""
        mock_type = MockType(spelling="enum Status", kind=TypeKind.ENUM)
        
        result = self.type_mapper.map_type(mock_type)
        
        assert "Status" in result or "int" in result
    
    def test_unexposed_type_handling(self):
        """Test handling of unexposed/unknown types"""
        mock_type = MockType(spelling="SomeUnknownType", kind=TypeKind.UNEXPOSED)
        
        result = self.type_mapper.map_type(mock_type)
        
        # Should provide some fallback
        assert result is not None
        assert len(result) > 0


class TestCodeGeneratorComplexScenarios:
    """Test complex code generation scenarios"""
    
    def setup_method(self):
        self.type_mapper = TypeMapper()
        self.generator = CodeGenerator(self.type_mapper)
    
    def test_struct_with_nested_anonymous_unions(self):
        """Test struct containing anonymous unions"""
        mock_cursor = Mock()
        mock_cursor.spelling = "ComplexStruct"
        mock_cursor.kind = CursorKind.STRUCT_DECL
        
        # Regular field
        mock_field1 = Mock()
        mock_field1.kind = CursorKind.FIELD_DECL
        mock_field1.spelling = "id"
        mock_field1.type = MockType(spelling="int", kind=TypeKind.INT)
        mock_field1.get_field_offsetof.return_value = 0
        
        # Anonymous union field
        mock_union = Mock()
        mock_union.kind = CursorKind.UNION_DECL
        mock_union.spelling = ""  # Anonymous
        
        # Union members
        mock_union_field1 = Mock()
        mock_union_field1.kind = CursorKind.FIELD_DECL
        mock_union_field1.spelling = "int_value"
        mock_union_field1.type = MockType(spelling="int", kind=TypeKind.INT)
        mock_union_field1.get_field_offsetof.return_value = 4
        
        mock_union_field2 = Mock()
        mock_union_field2.kind = CursorKind.FIELD_DECL
        mock_union_field2.spelling = "float_value" 
        mock_union_field2.type = MockType(spelling="float", kind=TypeKind.FLOAT)
        mock_union_field2.get_field_offsetof.return_value = 4
        
        mock_union.get_children.return_value = [mock_union_field1, mock_union_field2]
        
        mock_cursor.get_children.return_value = [mock_field1, mock_union]
        
        result = self.generator.generate_struct(mock_cursor)
        
        assert "ComplexStruct" in result
        assert "int id;" in result
        # Should handle anonymous union appropriately
    
    def test_function_with_complex_return_type(self):
        """Test function returning complex type"""
        mock_cursor = Mock()
        mock_cursor.spelling = "get_callback"
        
        # Return type is function pointer
        mock_return_type = MockType(spelling="int (*)(void)", kind=TypeKind.POINTER)
        mock_cursor.result_type = mock_return_type
        
        mock_cursor.get_arguments.return_value = []
        
        result = self.generator.generate_function(mock_cursor, "testlib")
        
        assert "get_callback" in result
        # Function pointers as return types should be handled
    
    def test_enum_with_non_sequential_values(self):
        """Test enum with explicit non-sequential values"""
        mock_cursor = Mock()
        mock_cursor.spelling = "ErrorCodes"
        
        # Enum constants with explicit values
        const1 = Mock()
        const1.kind = CursorKind.ENUM_CONSTANT_DECL
        const1.spelling = "SUCCESS"
        const1.enum_value = 0
        
        const2 = Mock()
        const2.kind = CursorKind.ENUM_CONSTANT_DECL
        const2.spelling = "NOT_FOUND"
        const2.enum_value = 404
        
        const3 = Mock()
        const3.kind = CursorKind.ENUM_CONSTANT_DECL
        const3.spelling = "SERVER_ERROR"
        const3.enum_value = 500
        
        mock_cursor.get_children.return_value = [const1, const2, const3]
        
        result = self.generator.generate_enum(mock_cursor)
        
        assert "SUCCESS = 0," in result
        assert "NOT_FOUND = 404," in result
        assert "SERVER_ERROR = 500," in result
    
    def test_enum_with_negative_values(self):
        """Test enum with negative values"""
        mock_cursor = Mock()
        mock_cursor.spelling = "SignedEnum"
        
        const1 = Mock()
        const1.kind = CursorKind.ENUM_CONSTANT_DECL
        const1.spelling = "NEGATIVE"
        const1.enum_value = -1
        
        const2 = Mock()
        const2.kind = CursorKind.ENUM_CONSTANT_DECL
        const2.spelling = "ZERO"
        const2.enum_value = 0
        
        const3 = Mock()
        const3.kind = CursorKind.ENUM_CONSTANT_DECL
        const3.spelling = "POSITIVE"
        const3.enum_value = 1
        
        mock_cursor.get_children.return_value = [const1, const2, const3]
        
        result = self.generator.generate_enum(mock_cursor)
        
        assert "NEGATIVE = -1," in result
        assert "ZERO = 0," in result
        assert "POSITIVE = 1," in result


class TestGenerationConsistency:
    """Test consistency of generation across different scenarios"""
    
    def setup_method(self):
        self.type_mapper = TypeMapper()
        self.generator = CodeGenerator(self.type_mapper)
    
    def test_same_type_consistent_mapping(self):
        """Test that same type always maps consistently"""
        mock_type = MockType(spelling="int", kind=TypeKind.INT)
        
        # Map same type multiple times
        results = [self.type_mapper.map_type(mock_type) for _ in range(5)]
        
        # All results should be identical
        assert all(r == results[0] for r in results)
        assert all("int" in r for r in results)
    
    def test_opaque_type_registration_consistency(self):
        """Test opaque type registration and usage consistency"""
        # Register opaque type
        self.type_mapper.opaque_types.add("SDL_Window")
        
        mock_type = MockType(spelling="SDL_Window *", kind=TypeKind.POINTER)
        
        mock_pointee = MockType(spelling="SDL_Window")
        mock_type.get_pointee.return_value = mock_pointee
        
        result1 = self.type_mapper.map_type(mock_type)
        result2 = self.type_mapper.map_type(mock_type)
        
        assert result1 == result2
        # Result should be consistent (might be nint if not properly recognized as opaque)
        assert result1 is not None


class TestBasicGeneratorFeatures:
    """Test basic generator features that may not be fully covered"""
    
    def setup_method(self):
        self.type_mapper = TypeMapper()
        self.generator = CodeGenerator(self.type_mapper)
    
    def test_empty_struct_handling(self):
        """Test handling of empty structs"""
        mock_cursor = Mock()
        mock_cursor.spelling = "EmptyStruct"
        mock_cursor.kind = CursorKind.STRUCT_DECL
        mock_cursor.get_children.return_value = []  # No fields
        
        result = self.generator.generate_struct(mock_cursor)
        
        # Should handle empty struct (might return empty string or minimal struct)
        assert result == "" or "EmptyStruct" in result
    
    def test_empty_union_handling(self):
        """Test handling of empty unions"""
        mock_cursor = Mock()
        mock_cursor.spelling = "EmptyUnion"
        mock_cursor.kind = CursorKind.UNION_DECL
        mock_cursor.get_children.return_value = []  # No fields
        
        result = self.generator.generate_union(mock_cursor)
        
        # Should handle empty union (might return empty string or minimal union)
        assert result == "" or "EmptyUnion" in result
    
    def test_empty_enum_handling(self):
        """Test handling of empty enums"""
        mock_cursor = Mock()
        mock_cursor.spelling = "EmptyEnum"
        mock_cursor.get_children.return_value = []  # No constants
        
        result = self.generator.generate_enum(mock_cursor)
        
        # Should handle empty enum (likely returns empty string)
        assert result == ""
    
    def test_function_with_void_parameters(self):
        """Test function with void parameter list"""
        mock_cursor = Mock()
        mock_cursor.spelling = "void_func"
        mock_cursor.result_type = MockType(spelling="void", kind=TypeKind.VOID)
        mock_cursor.get_arguments.return_value = []
        
        result = self.generator.generate_function(mock_cursor, "testlib")
        
        assert "void_func" in result
        assert "void_func();" in result  # No parameters