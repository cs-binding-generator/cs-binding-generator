"""
Integration tests for CSharpBindingsGenerator
"""

import pytest
from pathlib import Path

from cs_binding_generator.generator import CSharpBindingsGenerator


class TestCSharpBindingsGenerator:
    """Test the main CSharpBindingsGenerator class"""
    
    def test_generate_from_simple_header(self, temp_header_file):
        """Test generating bindings from a simple header file"""
        generator = CSharpBindingsGenerator("testlib")
        output = generator.generate([temp_header_file], namespace="Test")
        
        # Check basic structure
        assert "namespace Test;" in output
        assert "using System.Runtime.InteropServices;" in output
        
        # Check enum generation
        assert "public enum Status" in output
        assert "OK = 0," in output
        assert "ERROR = 1," in output
        assert "PENDING = 2," in output
        
        # Check struct generation
        assert "public struct Point" in output
        assert "public int x;" in output
        assert "public int y;" in output
        
        # Check function generation
        assert "public static partial int add(int a, int b);" in output
        assert "public static partial nint get_data();" in output
        assert "public static partial string get_name();" in output
        
        # Check LibraryImport attributes
        assert '[LibraryImport("testlib"' in output
    
    def test_generate_from_complex_header(self, complex_header_file):
        """Test generating bindings from a complex header file"""
        generator = CSharpBindingsGenerator("nativelib")
        output = generator.generate([complex_header_file], namespace="MyApp.Native")
        
        # Check namespace
        assert "namespace MyApp.Native;" in output
        
        # Check enums
        assert "public enum Color" in output
        assert "RED = 16711680," in output  # 0xFF0000
        assert "GREEN = 65280," in output   # 0x00FF00
        assert "BLUE = 255," in output      # 0x0000FF
        
        assert "public enum BuildMode" in output
        assert "MODE_NORMAL" in output
        assert "MODE_DEBUG" in output
        assert "MODE_RELEASE" in output
        
        # Check structs
        assert "public struct Vector3" in output
        assert "public float x;" in output
        assert "public float y;" in output
        assert "public float z;" in output
        
        # Check functions
        assert "public static partial void init_engine(string config_path);" in output
        assert "public static partial nint create_vector(float x, float y, float z);" in output
        assert "public static partial void destroy_vector(nint vec);" in output
        assert "public static partial float dot_product(nint a, nint b);" in output
        assert "public static partial ulong get_timestamp();" in output
    
    def test_generate_to_file(self, temp_header_file, tmp_path):
        """Test generating bindings to an output file"""
        generator = CSharpBindingsGenerator("mylib")
        output_file = tmp_path / "Bindings.cs"
        
        generator.generate([temp_header_file], output_file=str(output_file))
        
        # Verify file was created
        assert output_file.exists()
        
        # Verify content
        content = output_file.read_text()
        assert "namespace Bindings;" in content
        assert "public struct Point" in content
    
    def test_generate_multiple_headers(self, temp_header_file, complex_header_file):
        """Test generating bindings from multiple header files"""
        generator = CSharpBindingsGenerator("multilib")
        output = generator.generate(
            [temp_header_file, complex_header_file],
            namespace="Combined"
        )
        
        # Should contain elements from both headers
        assert "public struct Point" in output
        assert "public struct Vector3" in output
        assert "public enum Status" in output
        assert "public enum Color" in output
        assert "public static partial int add(int a, int b);" in output
        assert "public static partial void init_engine(string config_path);" in output
    
    def test_generate_nonexistent_file(self, capsys):
        """Test handling of nonexistent header files"""
        generator = CSharpBindingsGenerator("testlib")
        output = generator.generate(["/nonexistent/file.h"])
        
        # Should still generate valid output (empty)
        assert "namespace Bindings;" in output
        
        # Should print warning
        captured = capsys.readouterr()
        assert "Warning: Header file not found" in captured.err
    
    def test_custom_namespace(self, temp_header_file):
        """Test using custom namespace"""
        generator = CSharpBindingsGenerator("lib")
        output = generator.generate([temp_header_file], namespace="My.Custom.Namespace")
        
        assert "namespace My.Custom.Namespace;" in output
    
    def test_default_namespace(self, temp_header_file):
        """Test default namespace when not specified"""
        generator = CSharpBindingsGenerator("lib")
        output = generator.generate([temp_header_file])
        
        assert "namespace Bindings;" in output
    
    def test_library_name_in_attributes(self, temp_header_file):
        """Test that library name appears correctly in LibraryImport attributes"""
        generator = CSharpBindingsGenerator("my_custom_lib")
        output = generator.generate([temp_header_file])
        
        assert '[LibraryImport("my_custom_lib"' in output
    
    def test_struct_layout_attribute(self, temp_header_file):
        """Test that structs have StructLayout attribute"""
        generator = CSharpBindingsGenerator("lib")
        output = generator.generate([temp_header_file])
        
        assert "[StructLayout(LayoutKind.Sequential)]" in output


class TestGeneratorInternals:
    """Test internal methods of the generator"""
    
    def test_empty_generation(self):
        """Test generator with no parsed content"""
        generator = CSharpBindingsGenerator("emptylib")
        
        # Don't parse any files, just build output
        from cs_binding_generator.code_generators import OutputBuilder
        output = OutputBuilder.build(
            namespace="Empty",
            enums=[],
            structs=[],
            functions=[]
        )
        
        assert "namespace Empty;" in output
        assert "using System.Runtime.InteropServices;" in output
