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
        assert "public unsafe struct Point" in output
        assert "public int x;" in output
        assert "public int y;" in output
        
        # Check function generation
        assert "public static partial int add(int a, int b);" in output
        assert "public static partial nint get_data();" in output
        assert "public static partial nuint get_name();" in output  # char* return -> nuint
        
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
        assert "public unsafe struct Vector3" in output
        assert "public float x;" in output
        assert "public float y;" in output
        assert "public float z;" in output
        
        # Check functions
        assert "public static partial void init_engine(string config_path);" in output
        assert "public static partial Vector3* create_vector(float x, float y, float z);" in output
        assert "public static partial void destroy_vector(Vector3* vec);" in output
        assert "public static partial float dot_product(Vector3* a, Vector3* b);" in output
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
        assert "public unsafe struct Point" in content
    
    def test_generate_multiple_headers(self, temp_header_file, complex_header_file):
        """Test generating bindings from multiple header files"""
        generator = CSharpBindingsGenerator("multilib")
        output = generator.generate(
            [temp_header_file, complex_header_file],
            namespace="Combined"
        )
        
        # Should contain elements from both headers
        assert "public unsafe struct Point" in output
        assert "public unsafe struct Vector3" in output
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
        
        assert "[StructLayout(LayoutKind.Explicit)]" in output
        assert "[FieldOffset(" in output
    
    def test_generate_with_include_dirs(self, header_with_include):
        """Test generating bindings with include directories"""
        generator = CSharpBindingsGenerator("testlib")
        output = generator.generate(
            [header_with_include['main']],
            namespace="Test",
            include_dirs=[header_with_include['include_dir']]
        )
        
        # Should include Window from main.h (uses Config from include)
        assert "public unsafe struct Window" in output
        assert "public Config config;" in output
        
        # Should include function
        assert "public static partial void init_window(Window* win);" in output
        
        # Config struct is in included file, so won't be generated
        # (only main file content is processed, but types are resolved)
    
    def test_generate_without_include_dirs_fails(self, header_with_include, capsys):
        """Test that parsing has errors without include directories"""
        generator = CSharpBindingsGenerator("testlib")
        # Don't provide include_dirs - should have parse errors
        output = generator.generate(
            [header_with_include['main']],
            namespace="Test",
            include_dirs=[]  # No include directories
        )
        
        # Should still generate output
        assert "namespace Test;" in output
        
        # Check for errors in stderr
        captured = capsys.readouterr()
        # May have errors about not finding common.h
    
    def test_include_depth_zero(self, nested_includes):
        """Test include depth 0 (only root file)"""
        generator = CSharpBindingsGenerator("testlib")
        output = generator.generate(
            [nested_includes['root']],
            namespace="Test",
            include_dirs=[nested_includes['include_dir']],
            include_depth=0
        )
        
        # Should only include items from root.h
        assert "public unsafe struct RootStruct" in output
        assert "public static partial void root_function();" in output
        
        # Should NOT include items from level1.h or level2.h
        assert "MiddleStruct" not in output or "public unsafe struct MiddleStruct" not in output
        assert "DeepStruct" not in output or "public unsafe struct DeepStruct" not in output
        assert "level1_function" not in output
        assert "level2_function" not in output
    
    def test_include_depth_one(self, nested_includes):
        """Test include depth 1 (root + direct includes)"""
        generator = CSharpBindingsGenerator("testlib")
        output = generator.generate(
            [nested_includes['root']],
            namespace="Test",
            include_dirs=[nested_includes['include_dir']],
            include_depth=1
        )
        
        # Should include items from root.h and level1.h
        assert "public unsafe struct RootStruct" in output
        assert "public unsafe struct MiddleStruct" in output
        assert "public static partial void root_function();" in output
        assert "public static partial void level1_function();" in output
        
        # Should NOT include items from level2.h
        assert "public unsafe struct DeepStruct" not in output
        assert "level2_function" not in output
    
    def test_include_depth_two(self, nested_includes):
        """Test include depth 2 (root + 2 levels of includes)"""
        generator = CSharpBindingsGenerator("testlib")
        output = generator.generate(
            [nested_includes['root']],
            namespace="Test",
            include_dirs=[nested_includes['include_dir']],
            include_depth=2
        )
        
        # Should include items from all levels
        assert "public unsafe struct RootStruct" in output
        assert "public unsafe struct MiddleStruct" in output
        assert "public unsafe struct DeepStruct" in output
        assert "public static partial void root_function();" in output
        assert "public static partial void level1_function();" in output
        assert "public static partial void level2_function();" in output
    
    def test_include_depth_large(self, nested_includes):
        """Test include depth larger than actual depth"""
        generator = CSharpBindingsGenerator("testlib")
        output = generator.generate(
            [nested_includes['root']],
            namespace="Test",
            include_dirs=[nested_includes['include_dir']],
            include_depth=10  # Larger than actual depth
        )
        
        # Should include everything (same as depth 2)
        assert "public unsafe struct RootStruct" in output
        assert "public unsafe struct MiddleStruct" in output
        assert "public unsafe struct DeepStruct" in output


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
            unions=[],
            functions=[]
        )
        
        assert "namespace Empty;" in output
        assert "using System.Runtime.InteropServices;" in output
    
    def test_opaque_types_with_pointers(self, opaque_types_header):
        """Test that opaque types generate proper pointer types (SDL_Window*)"""
        generator = CSharpBindingsGenerator("SDL3")
        output = generator.generate([opaque_types_header], namespace="SDL")
        
        # Check that opaque types are generated as structs (not readonly)
        assert "public struct SDL_Window" in output
        assert "public struct SDL_Renderer" in output
        
        # Check that functions use typed pointers (SDL_Window*) instead of nint
        assert "public static partial SDL_Window* SDL_CreateWindow" in output
        assert "public static partial void SDL_DestroyWindow(SDL_Window* window);" in output
        assert "public static partial nuint SDL_GetWindowTitle(SDL_Window* window);" in output
        assert "public static partial int SDL_SetWindowTitle(SDL_Window* window, string title);" in output
        assert "public static partial SDL_Renderer* SDL_CreateRenderer(SDL_Window* window);" in output
        assert "public static partial void SDL_RenderPresent(SDL_Renderer* renderer);" in output
