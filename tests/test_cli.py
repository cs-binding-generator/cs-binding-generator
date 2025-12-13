"""
CLI integration tests
"""

import subprocess
import tempfile
from pathlib import Path
import pytest


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


def test_cli_with_include_directories():
    """Test CLI with include directories from XML"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create include directory
        include_dir = tmppath / "include"
        include_dir.mkdir()
        
        # Create a header in include directory
        (include_dir / "types.h").write_text("""
typedef struct Point {
    int x;
    int y;
} Point;
""")
        
        # Create main header that uses types from include
        main_header = tmppath / "main.h"
        main_header.write_text("""
#include "types.h"

void process_point(Point* p);
""")
        
        # Create XML config
        config_content = create_xml_config(
            [(str(main_header), "testlib")],
            namespace="Test",
            include_dirs=[str(include_dir)]
        )
        config_file = tmppath / "config.xml"
        config_file.write_text(config_content)
        
        # Create output directory
        output_dir = tmppath / "output"
        
        # Run the CLI
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "--config", str(config_file),
                "-o", str(output_dir)
            ],
            capture_output=True,
            text=True
        )
        
        # Check it succeeded
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        # Check output directory was created
        assert output_dir.exists(), "Output directory not created"
        assert output_dir.is_dir(), "Output should be a directory"
        
        # Check library file was created
        lib_file = output_dir / "testlib.cs"
        assert lib_file.exists(), "Library file not created"
        
        # Check content
        content = lib_file.read_text()
        assert "namespace Test;" in content
        assert "public static partial void process_point(Point* p);" in content


def test_cli_include_depth():
    """Test CLI with --include-depth flag"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create include directory
        include_dir = tmppath / "include"
        include_dir.mkdir()
        
        # Create level 1 header
        (include_dir / "base.h").write_text("""
typedef struct BaseType {
    int value;
} BaseType;
""")
        
        # Create main header that includes base.h
        main_header = tmppath / "main.h"
        main_header.write_text("""
#include "base.h"

typedef struct MainType {
    BaseType base;
} MainType;

void main_function();
""")
        
        # Create XML config
        config_content = create_xml_config(
            [(str(main_header), "lib")],
            include_dirs=[str(include_dir)]
        )
        config_file = tmppath / "config.xml"
        config_file.write_text(config_content)
        
        # Test with depth 0 (should only have MainType)
        output_dir = tmppath / "output0"
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "--config", str(config_file),
                "-o", str(output_dir),
                "--include-depth", "0"
            ],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        lib_file = output_dir / "lib.cs"
        content = lib_file.read_text()
        assert "MainType" in content
        assert "main_function" in content
        # BaseType should not be generated (it's in included file)
        assert "public partial struct BaseType" not in content
        
        # Test with depth 1 (should have both)
        config_file2 = tmppath / "config2.xml"
        config_file2.write_text(config_content)
        output_dir2 = tmppath / "output1"
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "--config", str(config_file2),
                "-o", str(output_dir2),
                "--include-depth", "1"
            ],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        lib_file2 = output_dir2 / "lib.cs"
        content2 = lib_file2.read_text()
        assert "MainType" in content2
        assert "BaseType" in content2
        assert "main_function" in content2


def test_sdl3_generates_valid_csharp():
    """Test that SDL3 headers generate valid C# code that compiles with dotnet"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create XML config for SDL3
        config_content = create_xml_config([("/usr/include/SDL3/SDL.h", "SDL3")])
        config_file = tmppath / "config.xml"
        config_file.write_text(config_content)
        
        # Create output directory
        output_dir = tmppath / "bindings"
        output_dir.mkdir()
        
        # Generate SDL3 bindings
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "--config", str(config_file),
                "-o", str(output_dir)
            ],
            capture_output=True,
            text=True
        )
        
        # Check generation succeeded
        assert result.returncode == 0, f"SDL3 generation failed: {result.stderr}"
        
        # Verify output files were created
        sdl3_file = output_dir / "SDL3.cs"
        assert sdl3_file.exists(), "SDL3.cs not created"
        
        # Create a minimal C# project to compile the bindings
        csproj = output_dir / "Test.csproj"
        csproj.write_text("""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Library</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
""")
        
        # Verify the C# file compiles with dotnet
        result = subprocess.run(
            ["dotnet", "build"],
            cwd=output_dir,
            capture_output=True,
            text=True
        )
        
        # Check compilation succeeded
        assert result.returncode == 0, f"C# compilation failed:\n{result.stdout}\n{result.stderr}"
        
        # Verify output contains success message
        assert "Build succeeded" in result.stdout or "Build SUCCEEDED" in result.stdout


def test_cli_missing_header_files():
    """Test CLI behavior with missing header files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create config that references missing file
        config_content = create_xml_config([("/nonexistent/file.h", "testlib")])
        config_file = tmppath / "config.xml"
        config_file.write_text(config_content)
        
        output_dir = tmppath / "output"
        
        # Test that CLI fails by default with missing file
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "--config", str(config_file),
                "-o", str(output_dir)
            ],
            capture_output=True,
            text=True
        )
        
        # Should fail
        assert result.returncode != 0
        assert "Error: Header file not found" in result.stderr

        # Test that CLI succeeds with --ignore-missing flag
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "--config", str(config_file),
                "-o", str(output_dir),
                "--ignore-missing"
            ],
            capture_output=True,
            text=True
        )
        
        # Should succeed but generate empty output
        assert result.returncode == 0
        assert "Warning: Header file not found" in result.stderr
        # Should still create output directory
        assert output_dir.exists()


if __name__ == "__main__":
    test_cli_with_include_directories()
    test_cli_multiple_include_dirs()
    test_cli_include_depth()
    test_sdl3_generates_valid_csharp()
    test_cli_missing_header_files()
    print("CLI tests passed!")
