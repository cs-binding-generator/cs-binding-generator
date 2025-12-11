"""
Unit tests for CodeGenerator and OutputBuilder
"""

import pytest
from unittest.mock import Mock, MagicMock
from clang.cindex import CursorKind, TypeKind

from cs_binding_generator.code_generators import CodeGenerator, OutputBuilder
from cs_binding_generator.type_mapper import TypeMapper


class TestCodeGenerator:
    """Test the CodeGenerator class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.type_mapper = TypeMapper()
        self.generator = CodeGenerator("mylib", self.type_mapper)
    
    def test_generate_simple_function(self):
        """Test generating a simple function with no parameters"""
        mock_cursor = Mock()
        mock_cursor.spelling = "get_version"
        
        mock_result_type = Mock()
        mock_result_type.kind = TypeKind.INT
        mock_cursor.result_type = mock_result_type
        
        mock_cursor.get_arguments.return_value = []
        
        result = self.generator.generate_function(mock_cursor)
        
        assert '[LibraryImport("mylib", EntryPoint = "get_version")]' in result
        assert "public static partial int get_version();" in result
    
    def test_generate_function_with_parameters(self):
        """Test generating a function with parameters"""
        mock_cursor = Mock()
        mock_cursor.spelling = "add"
        
        mock_result_type = Mock()
        mock_result_type.kind = TypeKind.INT
        mock_cursor.result_type = mock_result_type
        
        # Create mock arguments
        arg1 = Mock()
        arg1.spelling = "a"
        arg1_type = Mock()
        arg1_type.kind = TypeKind.INT
        arg1.type = arg1_type
        
        arg2 = Mock()
        arg2.spelling = "b"
        arg2_type = Mock()
        arg2_type.kind = TypeKind.INT
        arg2.type = arg2_type
        
        mock_cursor.get_arguments.return_value = [arg1, arg2]
        
        result = self.generator.generate_function(mock_cursor)
        
        assert '[LibraryImport("mylib", EntryPoint = "add")]' in result
        assert "public static partial int add(int a, int b);" in result
    
    def test_generate_function_unnamed_parameter(self):
        """Test generating a function with unnamed parameters"""
        mock_cursor = Mock()
        mock_cursor.spelling = "process"
        
        mock_result_type = Mock()
        mock_result_type.kind = TypeKind.VOID
        mock_cursor.result_type = mock_result_type
        
        # Create mock argument with no name
        arg1 = Mock()
        arg1.spelling = ""  # Unnamed parameter
        arg1_type = Mock()
        arg1_type.kind = TypeKind.INT
        arg1.type = arg1_type
        
        mock_cursor.get_arguments.return_value = [arg1]
        
        result = self.generator.generate_function(mock_cursor)
        
        assert "void process(int param0);" in result
    
    def test_generate_struct_simple(self):
        """Test generating a simple struct"""
        mock_cursor = Mock()
        mock_cursor.spelling = "Point"
        
        # Create mock fields
        field1 = Mock()
        field1.kind = CursorKind.FIELD_DECL
        field1.spelling = "x"
        field1_type = Mock()
        field1_type.kind = TypeKind.INT
        field1.type = field1_type
        
        field2 = Mock()
        field2.kind = CursorKind.FIELD_DECL
        field2.spelling = "y"
        field2_type = Mock()
        field2_type.kind = TypeKind.INT
        field2.type = field2_type
        
        mock_cursor.get_children.return_value = [field1, field2]
        
        result = self.generator.generate_struct(mock_cursor)
        
        assert "[StructLayout(LayoutKind.Sequential)]" in result
        assert "public struct Point" in result
        assert "public int x;" in result
        assert "public int y;" in result
    
    def test_generate_struct_empty(self):
        """Test that empty struct returns empty string"""
        mock_cursor = Mock()
        mock_cursor.spelling = "EmptyStruct"
        mock_cursor.get_children.return_value = []
        
        result = self.generator.generate_struct(mock_cursor)
        
        assert result == ""
    
    def test_generate_enum_simple(self):
        """Test generating a simple enum"""
        mock_cursor = Mock()
        mock_cursor.spelling = "Status"
        
        # Create mock enum constants
        const1 = Mock()
        const1.kind = CursorKind.ENUM_CONSTANT_DECL
        const1.spelling = "OK"
        const1.enum_value = 0
        
        const2 = Mock()
        const2.kind = CursorKind.ENUM_CONSTANT_DECL
        const2.spelling = "ERROR"
        const2.enum_value = 1
        
        mock_cursor.get_children.return_value = [const1, const2]
        
        result = self.generator.generate_enum(mock_cursor)
        
        assert "public enum Status" in result
        assert "OK = 0," in result
        assert "ERROR = 1," in result
    
    def test_generate_enum_anonymous(self):
        """Test generating an anonymous enum"""
        mock_cursor = Mock()
        mock_cursor.spelling = ""  # Anonymous
        
        const1 = Mock()
        const1.kind = CursorKind.ENUM_CONSTANT_DECL
        const1.spelling = "VALUE1"
        const1.enum_value = 100
        
        mock_cursor.get_children.return_value = [const1]
        
        result = self.generator.generate_enum(mock_cursor)
        
        assert "public enum AnonymousEnum" in result
        assert "VALUE1 = 100," in result
    
    def test_generate_enum_empty(self):
        """Test that empty enum returns empty string"""
        mock_cursor = Mock()
        mock_cursor.spelling = "EmptyEnum"
        mock_cursor.get_children.return_value = []
        
        result = self.generator.generate_enum(mock_cursor)
        
        assert result == ""


class TestOutputBuilder:
    """Test the OutputBuilder class"""
    
    def test_build_complete_output(self):
        """Test building complete C# output"""
        enums = ['public enum Status\n{\n    OK = 0,\n}\n']
        structs = ['[StructLayout(LayoutKind.Sequential)]\npublic struct Point\n{\n    public int x;\n}\n']
        functions = ['    [LibraryImport("mylib")]\n    public static partial int add(int a, int b);\n']
        
        result = OutputBuilder.build(
            namespace="MyApp.Bindings",
            enums=enums,
            structs=structs,
            functions=functions,
            class_name="NativeMethods"
        )
        
        assert "using System.Runtime.InteropServices;" in result
        assert "using System.Runtime.InteropServices.Marshalling;" in result
        assert "namespace MyApp.Bindings;" in result
        assert "public enum Status" in result
        assert "public struct Point" in result
        assert "public static unsafe partial class NativeMethods" in result
        assert "public static partial int add(int a, int b);" in result
    
    def test_build_minimal_output(self):
        """Test building output with only functions"""
        functions = ['    [LibraryImport("lib")]\n    public static partial void init();\n']
        
        result = OutputBuilder.build(
            namespace="Test",
            enums=[],
            structs=[],
            functions=functions
        )
        
        assert "namespace Test;" in result
        assert "public static unsafe partial class NativeMethods" in result
        assert "public static partial void init();" in result
    
    def test_build_empty_output(self):
        """Test building output with no content"""
        result = OutputBuilder.build(
            namespace="Empty",
            enums=[],
            structs=[],
            functions=[]
        )
        
        assert "namespace Empty;" in result
        assert "public static partial class" not in result
    
    def test_build_custom_class_name(self):
        """Test using custom class name for native methods"""
        functions = ['    [LibraryImport("lib")]\n    public static partial void test();\n']
        
        result = OutputBuilder.build(
            namespace="Test",
            enums=[],
            structs=[],
            functions=functions,
            class_name="CustomNative"
        )
        
        assert "public static unsafe partial class CustomNative" in result
