"""
Integration tests for CSharpBindingsGenerator
"""

import pytest
from pathlib import Path

from cs_binding_generator.generator import CSharpBindingsGenerator


class TestCSharpBindingsGenerator:
    """Test the main CSharpBindingsGenerator class"""
    
    def test_generate_from_simple_header(self, temp_header_file, tmp_path):
        """Test generating bindings from a simple header file"""
        output_dir = tmp_path / "output"
        generator = CSharpBindingsGenerator()
        result = generator.generate([(temp_header_file, "testlib")], output=str(output_dir))
        
        # Should return a dict of filename -> content
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        
        output = result["testlib.cs"]
        
        # Check basic structure
        assert "namespace Bindings;" in output  # Default namespace since no library namespace specified
        assert "using System.Runtime.InteropServices;" in output
        
        # Check enum generation
        assert "public enum Status" in output
        assert "OK = 0," in output
        assert "ERROR = 1," in output
        assert "PENDING = 2," in output
        
        # Check struct generation
        assert "public unsafe partial struct Point" in output
        assert "public int x;" in output
        assert "public int y;" in output
        
        # Check function generation
        assert "public static partial int add(int a, int b);" in output
        assert "public static partial nint get_data();" in output
        assert "public static partial nuint get_name();" in output  # char* return -> nuint
        
        # Check LibraryImport attributes
        assert '[LibraryImport("testlib"' in output
    
    def test_generate_from_complex_header(self, complex_header_file, tmp_path):
        """Test generating bindings from a complex header file"""
        output_dir = tmp_path / "output"
        generator = CSharpBindingsGenerator()
        result = generator.generate([(complex_header_file, "nativelib")], output=str(output_dir))
        
        assert isinstance(result, dict)
        assert "nativelib.cs" in result
        
        output = result["nativelib.cs"]
        
        # Check namespace (default since no library namespace specified)
        assert "namespace Bindings;" in output
        
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
        assert "public unsafe partial struct Vector3" in output
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
        """Test generating bindings to an output directory"""
        generator = CSharpBindingsGenerator()
        output_dir = tmp_path / "output"
        
        result = generator.generate([(temp_header_file, "testlib")], output=str(output_dir))
        
        # Should return dict of files
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        
        # Verify directory was created
        assert output_dir.exists()
        assert output_dir.is_dir()
        
        # Verify file was created
        output_file = output_dir / "testlib.cs"
        assert output_file.exists()
        
        # Verify content
        content = output_file.read_text()
        assert "namespace Bindings;" in content
        assert "public unsafe partial struct Point" in content
    
    def test_generate_multiple_headers(self, temp_header_file, complex_header_file, tmp_path):
        """Test generating bindings from multiple header files"""
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(temp_header_file, "testlib"), (complex_header_file, "nativelib")],
            output=str(tmp_path / "output"),
            library_namespaces={"testlib": "Combined", "nativelib": "Combined"}
        )
        
        # Should return dict of files
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        assert "nativelib.cs" in result
        
        # Combine all output for checking
        output = "\n".join(result.values())
        
        # Should contain elements from both headers
        assert "public unsafe partial struct Point" in output
        assert "public unsafe partial struct Vector3" in output
        assert "public enum Status" in output
        assert "public enum Color" in output
        assert "public static partial int add(int a, int b);" in output
        assert "public static partial void init_engine(string config_path);" in output
    
    def test_generate_nonexistent_file(self, capsys, tmp_path):
        """Test handling of nonexistent header files"""
        generator = CSharpBindingsGenerator()
        
        # Should raise FileNotFoundError by default
        with pytest.raises(FileNotFoundError) as excinfo:
            generator.generate([("/nonexistent/file.h", "testlib")], output=str(tmp_path / "output"))
        
        assert "Header file not found" in str(excinfo.value)
        assert "/nonexistent/file.h" in str(excinfo.value)
        
        # Should print error message
        captured = capsys.readouterr()
        assert "Error: Header file not found" in captured.err
    
    def test_generate_nonexistent_file_with_ignore_missing(self, capsys, tmp_path):
        """Test handling of nonexistent header files with ignore_missing=True"""
        generator = CSharpBindingsGenerator()
        result = generator.generate([("/nonexistent/file.h", "testlib")], output=str(tmp_path / "output"), ignore_missing=True)
        
        # Should return dict with just the assembly bindings file since no libraries were processed
        assert isinstance(result, dict)
        assert "bindings.cs" in result
        assert len(result) == 1  # Only the assembly bindings file
        
        # Should print warning
        captured = capsys.readouterr()
        assert "Warning: Header file not found" in captured.err
    
    def test_generate_mixed_existing_nonexistent_files(self, temp_header_file, capsys, tmp_path):
        """Test handling mix of existing and nonexistent files"""
        generator = CSharpBindingsGenerator()
        
        # Should fail by default if ANY file is missing
        with pytest.raises(FileNotFoundError):
            generator.generate([(temp_header_file, "testlib"), ("/nonexistent/file.h", "testlib")], output=str(tmp_path / "output"))
        
        # Should succeed with ignore_missing=True, processing only valid files
        result = generator.generate([(temp_header_file, "testlib"), ("/nonexistent/file.h", "testlib")], output=str(tmp_path / "output2"), ignore_missing=True)
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        output = result["testlib.cs"]
        assert "public unsafe partial struct Point" in output
        
        captured = capsys.readouterr()
        assert "Warning: Header file not found" in captured.err
    
    def test_custom_namespace(self, temp_header_file, tmp_path):
        """Test using custom namespace"""
        generator = CSharpBindingsGenerator()
        result = generator.generate([(temp_header_file, "testlib")], output=str(tmp_path / "output"), library_namespaces={"testlib": "My.Custom.Namespace"})
        
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        output = result["testlib.cs"]
        assert "namespace My.Custom.Namespace;" in output
    
    def test_default_namespace(self, temp_header_file, tmp_path):
        """Test default namespace when not specified"""
        generator = CSharpBindingsGenerator()
        result = generator.generate([(temp_header_file, "testlib")], output=str(tmp_path / "output"))
        
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        output = result["testlib.cs"]
        assert "namespace Bindings;" in output
    
    def test_library_name_in_attributes(self, temp_header_file, tmp_path):
        """Test that library name appears correctly in LibraryImport attributes"""
        generator = CSharpBindingsGenerator()
        result = generator.generate([(temp_header_file, "my_custom_lib")], output=str(tmp_path / "output"))
        
        assert isinstance(result, dict)
        assert "my_custom_lib.cs" in result
        output = result["my_custom_lib.cs"]
        assert '[LibraryImport("my_custom_lib"' in output
    
    def test_struct_layout_attribute(self, temp_header_file, tmp_path):
        """Test that structs have StructLayout attribute"""
        generator = CSharpBindingsGenerator()
        result = generator.generate([(temp_header_file, "testlib")], output=str(tmp_path / "output"))
        
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        output = result["testlib.cs"]
        assert "[StructLayout(LayoutKind.Explicit)]" in output
        assert "[FieldOffset(" in output
    
    def test_generate_with_include_dirs(self, header_with_include, tmp_path):
        """Test generating bindings with include directories"""
        generator = CSharpBindingsGenerator()
        output = generator.generate(
            [(header_with_include['main'], "testlib")],
            output=str(tmp_path),
            include_dirs=[header_with_include['include_dir']],
            library_namespaces={"testlib": "Test"}
        )
        
        # Should include Window from main.h (uses Config from include)
        assert "public unsafe partial struct Window" in output["testlib.cs"]
        assert "public Config config;" in output["testlib.cs"]
        
        # Should include function
        assert "public static partial void init_window(Window* win);" in output["testlib.cs"]
        
        # Config struct is in included file, so won't be generated
        # (only main file content is processed, but types are resolved)
    
    def test_generate_without_include_dirs_fails(self, header_with_include, tmp_path, capsys):
        """Test that parsing fails immediately with fatal errors when include directories are missing"""
        generator = CSharpBindingsGenerator()
        # Don't provide include_dirs - should have fatal parse errors
        
        with pytest.raises(RuntimeError) as exc_info:
            generator.generate(
                [(header_with_include['main'], "testlib")],
                output=str(tmp_path),
                library_namespaces={"testlib": "Test"},
                include_dirs=[]  # No include directories
            )
        
        # Should get a clear error message about missing includes
        error_msg = str(exc_info.value)
        assert "Fatal parsing errors" in error_msg
        assert "Check include directories" in error_msg
        assert "common.h" in error_msg  # The missing include file
        
        # Check for errors in stderr
        captured = capsys.readouterr()
        assert "common.h' file not found" in captured.err
    
    def test_include_depth_zero(self, nested_includes, tmp_path):
        """Test include depth 0 (only root file)"""
        generator = CSharpBindingsGenerator()
        output = generator.generate(
            [(nested_includes['root'], "testlib")],
            output=str(tmp_path),
            library_namespaces={"testlib": "Test"},
            include_dirs=[nested_includes['include_dir']],
            include_depth=0
        )
        
        # Should only include items from root.h
        assert "public unsafe partial struct RootStruct" in output["testlib.cs"]
        assert "public static partial void root_function();" in output["testlib.cs"]
        
        # Should NOT include items from level1.h or level2.h
        assert "MiddleStruct" not in output["testlib.cs"] or "public unsafe partial struct MiddleStruct" not in output["testlib.cs"]
        assert "DeepStruct" not in output["testlib.cs"] or "public unsafe partial struct DeepStruct" not in output["testlib.cs"]
        assert "level1_function" not in output["testlib.cs"]
        assert "level2_function" not in output["testlib.cs"]
    
    def test_include_depth_one(self, nested_includes, tmp_path):
        """Test include depth 1 (root + direct includes)"""
        generator = CSharpBindingsGenerator()
        output = generator.generate(
            [(nested_includes['root'], "testlib")],
            output=str(tmp_path),
            library_namespaces={"testlib": "Test"},
            include_dirs=[nested_includes['include_dir']],
            include_depth=1
        )
        
        # Should include items from root.h and level1.h
        assert "public unsafe partial struct RootStruct" in output["testlib.cs"]
        assert "public unsafe partial struct MiddleStruct" in output["testlib.cs"]
        assert "public static partial void root_function();" in output["testlib.cs"]
        assert "public static partial void level1_function();" in output["testlib.cs"]
        
        # Should NOT include items from level2.h
        assert "public unsafe partial struct DeepStruct" not in output["testlib.cs"]
        assert "level2_function" not in output["testlib.cs"]
    
    def test_include_depth_two(self, nested_includes, tmp_path):
        """Test include depth 2 (root + 2 levels of includes)"""
        generator = CSharpBindingsGenerator()
        output = generator.generate(
            [(nested_includes['root'], "testlib")],
            output=str(tmp_path),
            library_namespaces={"testlib": "Test"},
            include_dirs=[nested_includes['include_dir']],
            include_depth=2
        )
        
        # Should include items from all levels
        assert "public unsafe partial struct RootStruct" in output["testlib.cs"]
        assert "public unsafe partial struct MiddleStruct" in output["testlib.cs"]
        assert "public unsafe partial struct DeepStruct" in output["testlib.cs"]
        assert "public static partial void root_function();" in output["testlib.cs"]
        assert "public static partial void level1_function();" in output["testlib.cs"]
        assert "public static partial void level2_function();" in output["testlib.cs"]
    
    def test_include_depth_large(self, nested_includes, tmp_path):
        """Test include depth larger than actual depth"""
        generator = CSharpBindingsGenerator()
        output = generator.generate(
            [(nested_includes['root'], "testlib")],
            output=str(tmp_path),
            library_namespaces={"testlib": "Test"},
            include_dirs=[nested_includes['include_dir']],
            include_depth=10  # Larger than actual depth
        )
        
        # Should include everything (same as depth 2)
        assert "public unsafe partial struct RootStruct" in output["testlib.cs"]
        assert "public unsafe partial struct MiddleStruct" in output["testlib.cs"]
        assert "public unsafe partial struct DeepStruct" in output["testlib.cs"]


class TestGeneratorInternals:
    """Test internal methods of the generator"""
    
    def test_empty_generation(self):
        """Test generator with no parsed content"""
        generator = CSharpBindingsGenerator()
        
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
    
    def test_opaque_types_with_pointers(self, opaque_types_header, tmp_path):
        """Test that opaque types generate proper pointer types (SDL_Window*)"""
        generator = CSharpBindingsGenerator()
        output = generator.generate([(opaque_types_header, "testlib")], output=str(tmp_path), library_namespaces={"testlib": "SDL"})
        
        # Check that opaque types are generated as structs (not readonly)
        assert "public partial struct SDL_Window" in output["testlib.cs"]
        assert "public partial struct SDL_Renderer" in output["testlib.cs"]
        
        # Check that functions use typed pointers (SDL_Window*) instead of nint
        assert "public static partial SDL_Window* SDL_CreateWindow" in output["testlib.cs"]
        assert "public static partial void SDL_DestroyWindow(SDL_Window* window);" in output["testlib.cs"]
        assert "public static partial nuint SDL_GetWindowTitle(SDL_Window* window);" in output["testlib.cs"]
        assert "public static partial int SDL_SetWindowTitle(SDL_Window* window, string title);" in output["testlib.cs"]
        assert "public static partial SDL_Renderer* SDL_CreateRenderer(SDL_Window* window);" in output["testlib.cs"]
        assert "public static partial void SDL_RenderPresent(SDL_Renderer* renderer);" in output["testlib.cs"]
    
    def test_multi_file_generation(self, temp_dir, temp_header_file):
        """Test generating multiple files when multi_file=True"""
        generator = CSharpBindingsGenerator()
        
        # Create a second header file for another library
        header2_path = temp_dir / "header2.h"
        header2_path.write_text('''
            typedef enum {
                GRAPHICS_OK = 0,
                GRAPHICS_ERROR = 1
            } GraphicsStatus;
            
            int draw_line(int x1, int y1, int x2, int y2);
        ''')
        
        # Generate with multi-file output to temp directory
        result = generator.generate(
            [(temp_header_file, "testlib"), (header2_path, "graphics")], 
            output=str(temp_dir),
            library_namespaces={"testlib": "Test", "graphics": "Test"}
        )
        
        # Should return dict of filename -> content
        assert isinstance(result, dict)
        assert "testlib.cs" in result
        assert "graphics.cs" in result
        
        # Check testlib.cs content
        testlib_content = result["testlib.cs"]
        assert "namespace Test;" in testlib_content
        assert "public enum Status" in testlib_content
        assert "public static partial int add(int a, int b);" in testlib_content
        assert '[LibraryImport("testlib"' in testlib_content
        # Should NOT contain graphics content
        assert "GraphicsStatus" not in testlib_content
        assert "draw_line" not in testlib_content
        
        # Check graphics.cs content
        graphics_content = result["graphics.cs"]
        assert "namespace Test;" in graphics_content
        assert "public enum GraphicsStatus" in graphics_content  
        assert "public static partial int draw_line(int x1, int y1, int x2, int y2);" in graphics_content
        assert '[LibraryImport("graphics"' in graphics_content
        # Should NOT contain testlib content
        assert "enum Status" not in graphics_content
        assert "add(int a, int b)" not in graphics_content
    
    def test_single_file_vs_multi_file_content_consistency(self, temp_dir, temp_header_file, tmp_path):
        """Test that multi-file generation works correctly"""
        generator = CSharpBindingsGenerator()
        
        # Generate multi file output
        multi_output = generator.generate(
            [(temp_header_file, "testlib")], 
            output=str(tmp_path),
            library_namespaces={"testlib": "Test"}
        )
        
        # Multi output should have bindings.cs and testlib.cs
        assert isinstance(multi_output, dict)
        assert len(multi_output) == 2
        assert "bindings.cs" in multi_output
        assert "testlib.cs" in multi_output
        
        # Check that bindings.cs contains assembly attributes
        bindings_content = multi_output["bindings.cs"]
        assert "[assembly: System.Runtime.CompilerServices.DisableRuntimeMarshalling]" in bindings_content
        assert "namespace Bindings;" in bindings_content
        
        # Check that testlib.cs contains the actual bindings
        testlib_content = multi_output["testlib.cs"]
        assert "namespace Test;" in testlib_content
        assert "public enum Status" in testlib_content
        assert "public unsafe partial struct Point" in testlib_content
        assert "public static partial int add(int a, int b);" in testlib_content
        assert '[LibraryImport("testlib"' in testlib_content
    
    def test_multi_file_generation_with_custom_class_names(self, temp_dir, temp_header_file, tmp_path):
        """Test multi-file generation with custom class names"""
        generator = CSharpBindingsGenerator()
        
        # Create a second header file
        header2_path = temp_dir / "header2.h"
        header2_path.write_text('''
            typedef enum {
                GRAPHICS_OK = 0,
                GRAPHICS_ERROR = 1
            } GraphicsStatus;
            
            int draw_line(int x1, int y1, int x2, int y2);
        ''')
        
        # Generate with custom class names
        library_class_names = {"testlib": "CustomTestLib", "graphics": "CustomGraphics"}
        result = generator.generate(
            [(temp_header_file, "testlib"), (header2_path, "graphics")], 
            output=str(tmp_path),
            library_namespaces={"testlib": "Test", "graphics": "Test"},
            library_class_names=library_class_names
        )
        
        # Check testlib.cs uses custom class name
        testlib_content = result["testlib.cs"]
        assert "public static unsafe partial class CustomTestLib" in testlib_content
        assert "public static unsafe partial class NativeMethods" not in testlib_content
        
        # Check graphics.cs uses custom class name
        graphics_content = result["graphics.cs"]
        assert "public static unsafe partial class CustomGraphics" in graphics_content
        assert "public static unsafe partial class NativeMethods" not in graphics_content
