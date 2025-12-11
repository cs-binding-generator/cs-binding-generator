"""
CLI integration tests
"""

import subprocess
import tempfile
from pathlib import Path


def test_cli_with_include_directories():
    """Test CLI with -I flag for include directories"""
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
        
        # Create output file path
        output_file = tmppath / "output.cs"
        
        # Run the CLI
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "-i", str(main_header),
                "-I", str(include_dir),
                "-o", str(output_file),
                "-l", "testlib",
                "-n", "Test"
            ],
            capture_output=True,
            text=True
        )
        
        # Check it succeeded
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        # Check output file was created
        assert output_file.exists(), "Output file not created"
        
        # Check content
        content = output_file.read_text()
        assert "namespace Test;" in content
    assert "public static partial void process_point(Point* p);" in content
    """Test CLI with multiple -I flags"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create multiple include directories
        include1 = tmppath / "include1"
        include1.mkdir()
        include2 = tmppath / "include2"
        include2.mkdir()
        
        (include1 / "types.h").write_text("typedef int MyInt;")
        (include2 / "config.h").write_text("#define SIZE 100")
        
        # Create main header
        main_header = tmppath / "main.h"
        main_header.write_text("""
#include "types.h"
#include "config.h"

MyInt get_value();
""")
        
        # Run with multiple -I flags
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "-i", str(main_header),
                "-I", str(include1),
                "-I", str(include2),
                "-l", "lib"
            ],
            capture_output=True,
            text=True
        )
        
        # Should succeed
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        
        # Check output contains function
        assert "get_value" in result.stdout


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
        
        # Test with depth 0 (should only have MainType)
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "-i", str(main_header),
                "-I", str(include_dir),
                "-l", "lib",
                "--include-depth", "0"
            ],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "MainType" in result.stdout
        assert "main_function" in result.stdout
        # BaseType should not be generated (it's in included file)
        assert "public struct BaseType" not in result.stdout
        
        # Test with depth 1 (should have both)
        result = subprocess.run(
            [
                "python", "-m", "cs_binding_generator.main",
                "-i", str(main_header),
                "-I", str(include_dir),
                "-l", "lib",
                "--include-depth", "1"
            ],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "MainType" in result.stdout
        assert "BaseType" in result.stdout
        assert "main_function" in result.stdout


def test_sdl3_generates_valid_csharp():
    """Test that SDL3 headers generate valid C# code that compiles with dotnet"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Generate SDL3 bindings
        output_file = tmppath / "SDL3Bindings.cs"
        
        result = subprocess.run(
            [
                "cs_binding_generator",
                "-i", "/usr/include/SDL3/SDL.h",
                "-l", "SDL3",
                "-o", str(output_file),
                "--include-depth", "2",
                "-I", "/usr/include",
                "-I", "/usr/lib/clang/21/include"
            ],
            capture_output=True,
            text=True
        )
        
        # Check generation succeeded
        assert result.returncode == 0, f"SDL3 generation failed: {result.stderr}"
        assert output_file.exists(), "Output file not created"
        
        # Create a minimal C# project to compile the bindings
        csproj = tmppath / "Test.csproj"
        csproj.write_text("""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
""")
        
        # Verify the C# file compiles with dotnet
        result = subprocess.run(
            ["dotnet", "build"],
            cwd=tmppath,
            capture_output=True,
            text=True
        )
        
        # Check compilation succeeded
        assert result.returncode == 0, f"C# compilation failed:\n{result.stdout}\n{result.stderr}"
        
        # Verify output contains success message
        assert "Build succeeded" in result.stdout or "Build SUCCEEDED" in result.stdout


if __name__ == "__main__":
    test_cli_with_include_directories()
    test_cli_multiple_include_dirs()
    test_cli_include_depth()
    test_sdl3_generates_valid_csharp()
    print("CLI tests passed!")
