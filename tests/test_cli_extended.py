"""
Extended CLI and integration tests for better coverage
"""

import subprocess
import tempfile
import pytest
from pathlib import Path
import os
import json


def create_xml_config(header_files, namespace="Bindings", include_dirs=None):
    """Helper function to create XML config file for testing"""
    config_lines = ['<bindings>']
    
    for header, library in header_files:
        config_lines.append(f'  <library name="{library}" namespace="{namespace}">')
        config_lines.append(f'    <include file="{header}"/>')
        if include_dirs:
            for include_dir in include_dirs:
                config_lines.append(f'    <include_directory path="{include_dir}"/>')
        config_lines.append('  </library>')
    
    config_lines.append('</bindings>')
    return '\n'.join(config_lines)


class TestCLIIntegration:
    """Extended CLI integration tests"""
    
    def test_cli_help_output(self):
        """Test CLI help message"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main", "--help"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "Generate C# bindings from C header files" in result.stdout
        assert "--config" in result.stdout
        assert "--output" in result.stdout
    
    def test_cli_version_or_invalid_args(self):
        """Test CLI with no arguments"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main"
        ], capture_output=True, text=True)
        
        # Should show error about missing required arguments
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()
    
    def test_cli_single_file_output_to_stdout(self, temp_header_file, tmp_path):
        """Test CLI defaults output to current directory when not specified"""
        config_file = tmp_path / "config.xml"
        config_content = create_xml_config([(str(temp_header_file), "testlib")])
        config_file.write_text(config_content)

        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-C", str(config_file)
        ], capture_output=True, text=True, cwd=str(tmp_path))

        # Should succeed with output defaulting to current directory
        assert result.returncode == 0
        # Verify files were generated in current directory (tmp_path)
        assert (tmp_path / "testlib.cs").exists()
        assert (tmp_path / "bindings.cs").exists()
    
    def test_cli_custom_namespace(self, temp_header_file, tmp_path):
        """Test CLI with custom namespace"""
        config_file = tmp_path / "config.xml"
        config_content = create_xml_config([(str(temp_header_file), "testlib")], namespace="MyCustomNamespace")
        config_file.write_text(config_content)
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-C", str(config_file),
            "-o", str(output_dir)
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        testlib_file = output_dir / "testlib.cs"
        assert testlib_file.exists()
        content = testlib_file.read_text()
        assert "namespace MyCustomNamespace;" in content

    def test_cli_multi_file_output(self, tmp_path):
        """Test CLI multi-file output generation"""
        # Create headers for multiple libraries
        header1 = tmp_path / "lib1.h"
        header2 = tmp_path / "lib2.h"
        
        header1.write_text("int lib1_func(); typedef enum { LIB1_OK } lib1_status_t;")
        header2.write_text("int lib2_func(); typedef enum { LIB2_OK } lib2_status_t;")
        
        config_file = tmp_path / "config.xml"
        config_content = create_xml_config([
            (str(header1), "library1"),
            (str(header2), "library2")
        ], namespace="MultiTest")
        config_file.write_text(config_content)
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-C", str(config_file),
            "-o", str(output_dir)
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
    
    def test_cli_ignore_missing_flag(self, temp_header_file, tmp_path):
        """Test CLI with --ignore-missing flag"""
        config_file = tmp_path / "config.xml"
        config_content = create_xml_config([
            (str(temp_header_file), "testlib"),
            ("/nonexistent/file.h", "missing")
        ])
        config_file.write_text(config_content)
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-C", str(config_file),
            "-o", str(output_dir),
            "--ignore-missing"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        testlib_content = (output_dir / "testlib.cs").read_text()
        assert "add" in testlib_content  # Should process valid file
        # Should warn about missing file in stderr
        assert "Warning" in result.stderr or "warning" in result.stderr
    
    def test_cli_all_arguments_together(self, tmp_path):
        """Test CLI with all major arguments combined"""
        # Create complex test setup
        main_header = tmp_path / "main.h"
        include_dir = tmp_path / "includes"
        include_dir.mkdir()
        
        (include_dir / "types.h").write_text("typedef int MyInt;")
        main_header.write_text('#include "types.h"\nMyInt complex_func(MyInt a);')
        
        config_file = tmp_path / "config.xml"
        config_content = create_xml_config(
            [(str(main_header), "complexlib")],
            namespace="ComplexNamespace",
            include_dirs=[str(include_dir)]
        )
        config_file.write_text(config_content)
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-C", str(config_file),
            "-o", str(output_dir),
            "--ignore-missing"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        
        complexlib_file = output_dir / "complexlib.cs"
        assert complexlib_file.exists()
        
        content = complexlib_file.read_text()
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
        
        output_dir = temp_dir / "output"
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "--config", str(config_file),
            "-o", str(output_dir)
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert output_dir.exists()
        assert output_dir.is_dir()
        
        # Check that library-specific file was created
        lib_file = output_dir / "testlib.cs"
        assert lib_file.exists()
        
        content = lib_file.read_text()
        assert "namespace ConfigNamespace;" in content
        assert "config_test_func" in content
    
    def test_cli_missing_input_and_config(self, tmp_path):
        """Test that default config file must exist if not specified"""
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-o", str(tmp_path / "output")
        ], capture_output=True, text=True, cwd=str(tmp_path))

        assert result.returncode != 0
        assert "No config file specified and default 'cs-bindings.xml' not found" in result.stderr


class TestMultiFileGeneration:
    """Extended multi-file generation tests"""
    
    def test_multi_file_empty_library(self, tmp_path):
        """Test multi-file generation with library that has no content"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        generator = CSharpBindingsGenerator()
        
        # Create header with no parseable content
        empty_header = tmp_path / "empty.h" 
        empty_header.write_text("// Only comments\n#define MACRO 1")
        
        normal_header = tmp_path / "normal.h"
        normal_header.write_text("int normal_func();")
        
        result = generator.generate([
            (str(empty_header), "emptylib"),
            (str(normal_header), "normallib")
        ], output=str(tmp_path))
        
        assert isinstance(result, dict)
        # Should handle empty library gracefully
        if "emptylib.cs" in result:
            assert "namespace Bindings;" in result["emptylib.cs"]
        assert "normallib.cs" in result
        assert "normal_func" in result["normallib.cs"]
    
    def test_multi_file_identical_library_names(self, tmp_path):
        """Test multi-file generation with duplicate library names"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        generator = CSharpBindingsGenerator()
        
        header1 = tmp_path / "header1.h"
        header2 = tmp_path / "header2.h"
        
        header1.write_text("int func1();")
        header2.write_text("int func2();")
        
        # Both headers map to same library name
        result = generator.generate([
            (str(header1), "samelib"),
            (str(header2), "samelib")  # Duplicate name
        ], output=str(tmp_path))
        
        assert "samelib.cs" in result
        content = result["samelib.cs"]
        # Should combine both functions in same file
        assert "func1" in content
        assert "func2" in content
    
    def test_multi_file_special_characters_in_library_name(self, tmp_path):
        """Test multi-file with special characters in library name"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        generator = CSharpBindingsGenerator()
        
        header = tmp_path / "lib.h"
        header.write_text("int test_func();")
        
        # Library name with special characters
        result = generator.generate([
            (str(header), "lib-name.with.dots")
        ], output=str(tmp_path))
        
        # Should handle special characters (likely sanitized)
        assert len(result) > 0
        # File name should be sanitized for filesystem compatibility


class TestStringAndMarshallingEdgeCases:
    """Test string handling and marshalling edge cases"""
    
    def test_function_with_string_parameters(self, tmp_path):
        """Test functions with various string parameter types"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        header = tmp_path / "strings.h"
        header.write_text("""
        int process_string(const char* input);
        char* get_string(void);
        int multi_string(const char* input, char* output, const char* format);
        void wide_string(const wchar_t* wide);
        """)
        
        generator = CSharpBindingsGenerator()
        output = generator.generate([(str(header), "stringlib")], output=str(tmp_path))
        assert "nuint get_string" in output["stringlib.cs"]  # char* -> nuint (return value)
        assert "string format" in output["stringlib.cs"]  # multiple string params
        # Should handle various string types appropriately
    
    def test_struct_with_string_fields(self, tmp_path):
        """Test struct containing string/char pointer fields"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        header = tmp_path / "string_struct.h"
        header.write_text("""
        typedef struct {
            char* name;
            const char* description;
            char buffer[256];
            int length;
        } StringStruct;
        """)
        
        generator = CSharpBindingsGenerator()
        output = generator.generate([(str(header), "structlib")], output=str(tmp_path))
        
        assert "StringStruct" in output["structlib.cs"]
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