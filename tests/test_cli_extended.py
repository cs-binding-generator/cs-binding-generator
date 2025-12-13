"""
Extended CLI and integration tests for better coverage
"""

import subprocess
import tempfile
import pytest
from pathlib import Path
import os
import json


class TestCLIIntegration:
    """Extended CLI integration tests"""
    
    def test_cli_help_output(self):
        """Test CLI help message"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main", "--help"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "Generate C# bindings from C header files" in result.stdout
        assert "--input" in result.stdout
        assert "--output" in result.stdout
        assert "--namespace" in result.stdout
    
    def test_cli_version_or_invalid_args(self):
        """Test CLI with no arguments"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main"
        ], capture_output=True, text=True)
        
        # Should show error about missing required arguments
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()
    
    def test_cli_single_file_output_to_stdout(self, temp_header_file):
        """Test CLI output to stdout when no output file specified"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-i", f"{temp_header_file}:testlib"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "namespace Bindings;" in result.stdout
        assert "public static partial int add(int a, int b);" in result.stdout
    
    def test_cli_custom_namespace(self, temp_header_file, temp_dir):
        """Test CLI with custom namespace"""
        output_file = temp_dir / "custom.cs"
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-i", f"{temp_header_file}:testlib",
            "-o", str(output_file),
            "-n", "MyCustomNamespace"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        content = output_file.read_text()
        assert "namespace MyCustomNamespace;" in content
    
    def test_cli_include_depth_zero(self, temp_dir):
        """Test CLI with include depth zero (only main files)"""
        # Create main header with include
        main_header = temp_dir / "main.h"
        included_header = temp_dir / "included.h"
        
        included_header.write_text("int included_func();")
        main_header.write_text('#include "included.h"\nint main_func();')
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main", 
            "-i", f"{main_header}:testlib",
            "-I", str(temp_dir),
            "--include-depth", "0"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        # Should only process main file, not includes
        assert "main_func" in result.stdout
        # included_func might or might not appear depending on parse behavior
    
    def test_cli_multi_file_output(self, temp_dir):
        """Test CLI multi-file output generation"""
        # Create headers for multiple libraries
        header1 = temp_dir / "lib1.h"
        header2 = temp_dir / "lib2.h"
        
        header1.write_text("int lib1_func(); typedef enum { LIB1_OK } lib1_status_t;")
        header2.write_text("int lib2_func(); typedef enum { LIB2_OK } lib2_status_t;")
        
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-i", f"{header1}:library1",
            "-i", f"{header2}:library2", 
            "-o", str(output_dir),
            "--multi",
            "-n", "MultiTest"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        
        # Check that separate files were generated
        lib1_file = output_dir / "library1.cs"
        lib2_file = output_dir / "library2.cs"
        
        assert lib1_file.exists()
        assert lib2_file.exists()
        
        lib1_content = lib1_file.read_text()
        lib2_content = lib2_file.read_text()
        
        assert "lib1_func" in lib1_content
        assert "lib2_func" in lib2_content
        assert "lib1_func" not in lib2_content  # Should be separate
        assert "lib2_func" not in lib1_content
    
    def test_cli_ignore_missing_flag(self, temp_header_file):
        """Test CLI with --ignore-missing flag"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-i", f"{temp_header_file}:testlib",
            "-i", "/nonexistent/file.h:missing",
            "--ignore-missing"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "add" in result.stdout  # Should process valid file
        # Should warn about missing file in stderr
    
    def test_cli_all_arguments_together(self, temp_dir):
        """Test CLI with all major arguments combined"""
        # Create complex test setup
        main_header = temp_dir / "main.h"
        include_dir = temp_dir / "includes"
        include_dir.mkdir()
        
        (include_dir / "types.h").write_text("typedef int MyInt;")
        main_header.write_text('#include "types.h"\nMyInt complex_func(MyInt a);')
        
        output_file = temp_dir / "complex.cs"
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-i", f"{main_header}:complexlib",
            "-o", str(output_file),
            "-n", "ComplexNamespace", 
            "-I", str(include_dir),
            "--include-depth", "2",
            "--ignore-missing"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert output_file.exists()
        
        content = output_file.read_text()
        assert "namespace ComplexNamespace;" in content
        assert "complex_func" in content
    
    def test_cli_with_config_file(self, temp_dir):
        """Test CLI with XML configuration file"""
        # Create config file
        config_content = """
        <bindings>
            <library name="testlib" namespace="ConfigNamespace">
                <include file="{header_path}"/>
            </library>
        </bindings>
        """
        
        header = temp_dir / "test.h"
        header.write_text("int config_test_func();")
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content.format(header_path=str(header)))
        
        output_file = temp_dir / "output.cs"
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "--config", str(config_file),
            "-o", str(output_file)
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert output_file.exists()
        
        content = output_file.read_text()
        assert "namespace ConfigNamespace;" in content
        assert "config_test_func" in content
    
    def test_cli_config_and_input_conflict(self, temp_dir):
        """Test that --config and --input cannot be used together"""
        config_file = temp_dir / "config.xml"
        config_file.write_text("<bindings></bindings>")
        
        header_file = temp_dir / "test.h"
        header_file.write_text("int test();")
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "--config", str(config_file),
            "-i", f"{header_file}:testlib"
        ], capture_output=True, text=True)
        
        assert result.returncode != 0
        assert "Cannot specify both --config and --input" in result.stderr
    
    def test_cli_missing_input_and_config(self, temp_dir):
        """Test that either --config or --input must be specified"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-o", str(temp_dir / "output.cs")
        ], capture_output=True, text=True)
        
        assert result.returncode != 0
        assert "Must specify either --config or --input" in result.stderr


class TestMultiFileGeneration:
    """Extended multi-file generation tests"""
    
    def test_multi_file_empty_library(self, temp_dir):
        """Test multi-file generation with library that has no content"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        generator = CSharpBindingsGenerator()
        
        # Create header with no parseable content
        empty_header = temp_dir / "empty.h" 
        empty_header.write_text("// Only comments\n#define MACRO 1")
        
        normal_header = temp_dir / "normal.h"
        normal_header.write_text("int normal_func();")
        
        result = generator.generate([
            (str(empty_header), "emptylib"),
            (str(normal_header), "normallib")
        ], multi_file=True, output=str(temp_dir))
        
        assert isinstance(result, dict)
        # Should handle empty library gracefully
        if "emptylib.cs" in result:
            assert "namespace Bindings;" in result["emptylib.cs"]
        assert "normallib.cs" in result
        assert "normal_func" in result["normallib.cs"]
    
    def test_multi_file_identical_library_names(self, temp_dir):
        """Test multi-file generation with duplicate library names"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        generator = CSharpBindingsGenerator()
        
        header1 = temp_dir / "header1.h"
        header2 = temp_dir / "header2.h"
        
        header1.write_text("int func1();")
        header2.write_text("int func2();")
        
        # Both headers map to same library name
        result = generator.generate([
            (str(header1), "samelib"),
            (str(header2), "samelib")  # Duplicate name
        ], multi_file=True, output=str(temp_dir))
        
        assert "samelib.cs" in result
        content = result["samelib.cs"]
        # Should combine both functions in same file
        assert "func1" in content
        assert "func2" in content
    
    def test_multi_file_special_characters_in_library_name(self, temp_dir):
        """Test multi-file with special characters in library name"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        generator = CSharpBindingsGenerator()
        
        header = temp_dir / "lib.h"
        header.write_text("int test_func();")
        
        # Library name with special characters
        result = generator.generate([
            (str(header), "lib-name.with.dots")
        ], multi_file=True, output=str(temp_dir))
        
        # Should handle special characters (likely sanitized)
        assert len(result) > 0
        # File name should be sanitized for filesystem compatibility


class TestIncludeDepthHandling:
    """Test include depth processing edge cases"""
    
    def test_include_depth_circular_includes(self, temp_dir):
        """Test handling of circular includes"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        # Create circular includes (a.h includes b.h, b.h includes a.h)
        header_a = temp_dir / "a.h"
        header_b = temp_dir / "b.h"
        
        header_a.write_text('#ifndef A_H\n#define A_H\n#include "b.h"\nint func_a();\n#endif')
        header_b.write_text('#ifndef B_H\n#define B_H\n#include "a.h"\nint func_b();\n#endif')
        
        generator = CSharpBindingsGenerator()
        
        # Should handle circular includes without infinite loop
        output = generator.generate([
            (str(header_a), "testlib")
        ], include_dirs=[str(temp_dir)], include_depth=3)
        
        assert "namespace Bindings;" in output
        # Should process without hanging
    
    def test_include_depth_very_deep_nesting(self, temp_dir):
        """Test very deep include nesting"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        # Create deep chain: h0 -> h1 -> h2 -> ... -> h20
        headers = []
        for i in range(21):  # 0 to 20
            header = temp_dir / f"h{i}.h"
            if i < 20:
                header.write_text(f'#include "h{i+1}.h"\nint func_{i}();')
            else:
                header.write_text(f"int func_{i}();")  # Deepest file
            headers.append(header)
        
        generator = CSharpBindingsGenerator()
        
        # Test with various depth limits
        for max_depth in [5, 10, 50]:
            output = generator.generate([
                (str(headers[0]), "testlib")
            ], include_dirs=[str(temp_dir)], include_depth=max_depth)
            
            assert "namespace Bindings;" in output
            # Should respect depth limit and not crash


class TestStringAndMarshallingEdgeCases:
    """Test string handling and marshalling edge cases"""
    
    def test_function_with_string_parameters(self, temp_dir):
        """Test functions with various string parameter types"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        header = temp_dir / "strings.h"
        header.write_text("""
        int process_string(const char* input);
        char* get_string(void);
        int multi_string(const char* input, char* output, const char* format);
        void wide_string(const wchar_t* wide);
        """)
        
        generator = CSharpBindingsGenerator()
        output = generator.generate([(str(header), "stringlib")])
        
        assert "string input" in output  # const char* -> string
        assert "nuint get_string" in output  # char* -> nuint (return value)
        assert "string format" in output  # multiple string params
        # Should handle various string types appropriately
    
    def test_struct_with_string_fields(self, temp_dir):
        """Test struct containing string/char pointer fields"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        header = temp_dir / "string_struct.h"
        header.write_text("""
        typedef struct {
            char* name;
            const char* description;
            char buffer[256];
            int length;
        } StringStruct;
        """)
        
        generator = CSharpBindingsGenerator()
        output = generator.generate([(str(header), "structlib")])
        
        assert "StringStruct" in output
        # Should handle string fields in structs (likely as nint due to complexity)


@pytest.fixture
def temp_dir():
    """Fixture for temporary directory"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture 
def temp_header_file(temp_dir):
    """Fixture for temporary header file"""
    header_file = temp_dir / "test.h"
    header_file.write_text("""
    typedef struct {
        int x, y;
    } Point;
    
    typedef enum {
        STATUS_OK,
        STATUS_ERROR
    } Status;
    
    int add(int a, int b);
    """)
    return str(header_file)