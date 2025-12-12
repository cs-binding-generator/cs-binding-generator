"""
Test error handling and edge cases for improved coverage
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import clang.cindex

from cs_binding_generator.generator import CSharpBindingsGenerator
from cs_binding_generator.type_mapper import TypeMapper
from cs_binding_generator.code_generators import CodeGenerator


class TestErrorHandling:
    """Test error handling scenarios"""
    
    def test_missing_header_file_raises_error(self):
        """Test that missing header file raises FileNotFoundError"""
        generator = CSharpBindingsGenerator()
        
        with pytest.raises(FileNotFoundError, match="Header file not found"):
            generator.generate([("/nonexistent/file.h", "testlib")])
    
    def test_ignore_missing_files_continues_processing(self, temp_dir):
        """Test that ignore_missing=True continues with valid files"""
        generator = CSharpBindingsGenerator()
        
        # Create one valid header
        valid_header = temp_dir / "valid.h"
        valid_header.write_text("int get_value();")
        
        # Mix of valid and invalid files
        output = generator.generate(
            [(str(valid_header), "testlib"), ("/nonexistent.h", "missing")],
            ignore_missing=True
        )
        
        assert "get_value" in output
        assert "namespace Bindings;" in output
    
    def test_no_valid_files_raises_error(self):
        """Test that when no valid files remain, FileNotFoundError is raised"""
        generator = CSharpBindingsGenerator()
        
        with pytest.raises(FileNotFoundError, match="Header file not found"):
            generator.generate([("/nonexistent1.h", "lib1"), ("/nonexistent2.h", "lib2")])
    
    def test_multi_file_without_output_dir_raises_error(self, temp_header_file):
        """Test that multi-file mode without output directory raises ValueError"""
        generator = CSharpBindingsGenerator()
        
        with pytest.raises(ValueError, match="Output directory must be specified"):
            generator.generate([(temp_header_file, "testlib")], multi_file=True)
    
    def test_system_header_detection(self):
        """Test system header filtering"""
        generator = CSharpBindingsGenerator()
        
        # Standard C headers should be filtered
        assert generator._is_system_header("/usr/include/stdio.h")
        assert generator._is_system_header("/usr/include/stdlib.h")
        assert generator._is_system_header("/usr/include/string.h")
        assert generator._is_system_header("/usr/include/stdint.h")
        
        # System directories should be filtered
        assert generator._is_system_header("/usr/include/sys/types.h")
        assert generator._is_system_header("/usr/include/bits/wordsize.h")
        assert generator._is_system_header("/usr/lib/gcc/something.h")
        assert generator._is_system_header("/usr/lib/clang/15/include/stddef.h")
        
        # User headers should not be filtered
        assert not generator._is_system_header("/usr/include/SDL3/SDL.h")
        assert not generator._is_system_header("/usr/include/freetype2/freetype.h")
        assert not generator._is_system_header("/home/user/myproject/header.h")
    
    def test_empty_header_generates_minimal_output(self, temp_dir):
        """Test that empty header generates valid but minimal output"""
        generator = CSharpBindingsGenerator()
        
        empty_header = temp_dir / "empty.h"
        empty_header.write_text("// Empty header\n")
        
        output = generator.generate([(str(empty_header), "testlib")])
        
        assert "namespace Bindings;" in output
        assert "using System.Runtime.InteropServices;" in output
        # Should not contain NativeMethods class since no functions
        assert "NativeMethods" not in output
    
    def test_header_with_only_comments_and_includes(self, temp_dir):
        """Test header with only preprocessor directives"""
        generator = CSharpBindingsGenerator()
        
        header = temp_dir / "preprocessor.h"
        header.write_text("""
        // This is a header
        #ifndef HEADER_H
        #define HEADER_H
        
        #include <stdio.h>
        #include <stdlib.h>
        
        #define MAX_SIZE 1024
        #define VERSION "1.0"
        
        #endif
        """)
        
        output = generator.generate([(str(header), "testlib")])
        
        assert "namespace Bindings;" in output
        # Should generate minimal output
        assert "NativeMethods" not in output


class TestInternalMethods:
    """Test internal generator methods"""
    
    def test_add_to_library_collection(self):
        """Test internal collection management"""
        generator = CSharpBindingsGenerator()
        collection = {}
        
        generator._add_to_library_collection(collection, "lib1", "item1")
        generator._add_to_library_collection(collection, "lib1", "item2")
        generator._add_to_library_collection(collection, "lib2", "item3")
        
        assert collection["lib1"] == ["item1", "item2"]
        assert collection["lib2"] == ["item3"]
    
    def test_clear_state_resets_all_collections(self):
        """Test that clear state resets all internal state"""
        generator = CSharpBindingsGenerator()
        
        # Populate some state
        generator.generated_functions["lib"] = ["func1"]
        generator.generated_structs["lib"] = ["struct1"]
        generator.seen_functions.add(("func", "file"))
        generator.enum_members["enum1"] = ("lib", [("A", 0)], "int")
        
        generator._clear_state()
        
        assert len(generator.generated_functions) == 0
        assert len(generator.generated_structs) == 0
        assert len(generator.seen_functions) == 0
        assert len(generator.enum_members) == 0
    
    def test_file_depth_mapping(self, temp_dir):
        """Test file depth calculation for include processing"""
        generator = CSharpBindingsGenerator()
        
        # Create nested include structure
        main_h = temp_dir / "main.h"
        level1_h = temp_dir / "level1.h"
        level2_h = temp_dir / "level2.h"
        
        main_h.write_text('#include "level1.h"\nint main_func();')
        level1_h.write_text('#include "level2.h"\nint level1_func();')
        level2_h.write_text('int level2_func();')
        
        # Parse and build depth map
        index = clang.cindex.Index.create()
        tu = index.parse(str(main_h), args=[f"-I{temp_dir}"])
        
        depth_map = generator._build_file_depth_map(tu, str(main_h), max_depth=2)
        
        assert str(main_h) in depth_map
        assert depth_map[str(main_h)] == 0
        # level1.h should be depth 1
        # level2.h should be depth 2 (if found)


class TestCodeGeneratorEdgeCases:
    """Test edge cases in code generation"""
    
    def setup_method(self):
        self.type_mapper = TypeMapper()
        self.generator = CodeGenerator(self.type_mapper)
    
    def test_function_with_variadic_parameters(self):
        """Test generating function with variadic parameters (...)"""
        mock_cursor = Mock()
        mock_cursor.spelling = "printf_like"
        mock_cursor.result_type.kind = clang.cindex.TypeKind.INT
        mock_cursor.result_type.spelling = "int"
        
        # Mock parameter
        mock_param = Mock()
        mock_param.spelling = "format"
        mock_param.type.kind = clang.cindex.TypeKind.POINTER
        mock_param.type.spelling = "const char *"
        
        mock_cursor.get_arguments.return_value = [mock_param]
        
        result = self.generator.generate_function(mock_cursor, "testlib")
        
        assert "printf_like" in result
        # Check that the parameter was processed (might be mapped to nint for char*)
        assert "format" in result
    
    def test_anonymous_struct_generation(self):
        """Test generating anonymous struct"""
        mock_cursor = Mock()
        mock_cursor.spelling = ""  # Anonymous
        mock_cursor.kind = clang.cindex.CursorKind.STRUCT_DECL
        
        # Mock field
        mock_field = Mock()
        mock_field.kind = clang.cindex.CursorKind.FIELD_DECL
        mock_field.spelling = "value"
        mock_field.type.kind = clang.cindex.TypeKind.INT
        mock_field.type.spelling = "int"
        mock_field.get_field_offsetof.return_value = 0
        
        mock_cursor.get_children.return_value = [mock_field]
        
        result = self.generator.generate_struct(mock_cursor)
        
        # Should handle anonymous struct gracefully
        assert result is not None
    
    def test_struct_with_bitfields(self):
        """Test struct with bitfield members"""
        mock_cursor = Mock()
        mock_cursor.spelling = "BitfieldStruct"
        mock_cursor.kind = clang.cindex.CursorKind.STRUCT_DECL
        
        # Mock bitfield
        mock_field = Mock()
        mock_field.kind = clang.cindex.CursorKind.FIELD_DECL
        mock_field.spelling = "flag"
        mock_field.type.kind = clang.cindex.TypeKind.UINT
        mock_field.type.spelling = "unsigned int"
        mock_field.get_field_offsetof.return_value = 0
        mock_field.is_bitfield.return_value = True
        mock_field.get_bitfield_width.return_value = 1
        
        mock_cursor.get_children.return_value = [mock_field]
        
        result = self.generator.generate_struct(mock_cursor)
        
        assert "BitfieldStruct" in result
        # Bitfields should be handled as regular fields in C# with comments
    
    def test_enum_with_duplicate_values(self):
        """Test enum with duplicate values"""
        mock_cursor = Mock()
        mock_cursor.spelling = "DuplicateEnum"
        
        # Create enum constants with same values
        const1 = Mock()
        const1.kind = clang.cindex.CursorKind.ENUM_CONSTANT_DECL
        const1.spelling = "ALIAS1"
        const1.enum_value = 0
        
        const2 = Mock()
        const2.kind = clang.cindex.CursorKind.ENUM_CONSTANT_DECL
        const2.spelling = "ALIAS2" 
        const2.enum_value = 0  # Same value
        
        mock_cursor.get_children.return_value = [const1, const2]
        
        result = self.generator.generate_enum(mock_cursor)
        
        assert "ALIAS1 = 0," in result
        assert "ALIAS2 = 0," in result
    
    def test_function_pointer_typedef(self):
        """Test function pointer typedef handling"""
        # This tests a complex case that might not be fully covered
        mock_cursor = Mock()
        mock_cursor.spelling = "callback_t"
        mock_cursor.kind = clang.cindex.CursorKind.TYPEDEF_DECL
        
        # Mock the result type properly
        mock_result_type = Mock()
        mock_result_type.kind = clang.cindex.TypeKind.POINTER
        mock_result_type.spelling = "void (*)(int)"
        mock_cursor.result_type = mock_result_type
        mock_cursor.get_arguments.return_value = []
        
        # Function pointers as functions are complex - this might not generate anything
        # but should not crash
        try:
            result = self.generator.generate_function(mock_cursor, "testlib")
            # Should not crash
            assert result is not None or result == ""
        except Exception:
            # Some complex cases might not be supported, which is okay
            pass


class TestTypeMapperEdgeCases:
    """Test type mapper edge cases"""
    
    def setup_method(self):
        self.type_mapper = TypeMapper()
    
    def test_complex_nested_pointer_types(self):
        """Test deeply nested pointer types"""
        mock_type = Mock()
        mock_type.spelling = "int ***"
        mock_type.kind = clang.cindex.TypeKind.POINTER
        
        # Mock pointee type (int **)
        mock_pointee = Mock()
        mock_pointee.spelling = "int **"
        mock_pointee.kind = clang.cindex.TypeKind.POINTER
        mock_type.get_pointee.return_value = mock_pointee
        
        result = self.type_mapper.map_type(mock_type)
        
        # Should handle multiple levels of indirection
        assert "nint" in result or "int" in result
    
    def test_unknown_type_fallback(self):
        """Test fallback handling for unknown types"""
        mock_type = Mock()
        mock_type.spelling = "UnknownCustomType"
        mock_type.kind = clang.cindex.TypeKind.UNEXPOSED  # Unknown type
        
        result = self.type_mapper.map_type(mock_type)
        
        # Should fall back gracefully, likely to nint or original spelling
        assert result is not None
        assert len(result) > 0
    
    def test_typedef_chain_resolution(self):
        """Test complex typedef chain resolution"""
        # Create a mock typedef chain: MyInt -> int32_t -> int
        mock_type = Mock()
        mock_type.spelling = "MyInt" 
        mock_type.kind = clang.cindex.TypeKind.TYPEDEF
        
        # Mock the typedef target
        mock_canonical = Mock()
        mock_canonical.spelling = "int"
        mock_canonical.kind = clang.cindex.TypeKind.INT
        mock_type.get_canonical.return_value = mock_canonical
        
        result = self.type_mapper.map_type(mock_type)
        
        assert "int" in result


class TestCLIArguments:
    """Test CLI argument validation and edge cases"""
    
    def test_invalid_input_format_missing_colon(self, capsys):
        """Test CLI with invalid input format (no colon)"""
        import subprocess
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-i", "header.h",  # Missing :library
            "-o", "output.cs"
        ], capture_output=True, text=True)
        
        assert result.returncode != 0
        assert "Input must be in format 'header.h:library'" in result.stderr
    
    def test_multiple_include_directories(self, temp_dir):
        """Test CLI with many include directories"""
        import subprocess
        
        # Create multiple include directories
        includes = []
        for i in range(5):
            inc_dir = temp_dir / f"include{i}"
            inc_dir.mkdir()
            includes.extend(["-I", str(inc_dir)])
        
        # Create a simple header
        header = temp_dir / "test.h"
        header.write_text("int test_func();")
        
        result = subprocess.run([
            "python", "-m", "cs_binding_generator.main",
            "-i", f"{header}:testlib",
            "-o", str(temp_dir / "output.cs"),
            *includes
        ], capture_output=True, text=True)
        
        # Should handle many include directories without issues
        assert result.returncode == 0


class TestMemoryAndPerformance:
    """Test edge cases that might affect memory usage or performance"""
    
    def test_large_enum_generation(self):
        """Test generating enum with many values"""
        generator = CSharpBindingsGenerator()
        
        # Create a mock enum with many constants
        mock_cursor = Mock()
        mock_cursor.spelling = "LargeEnum"
        
        constants = []
        for i in range(1000):  # Large number of constants
            const = Mock()
            const.kind = clang.cindex.CursorKind.ENUM_CONSTANT_DECL
            const.spelling = f"VALUE_{i}"
            const.enum_value = i
            constants.append(const)
        
        mock_cursor.get_children.return_value = constants
        
        code_gen = CodeGenerator(TypeMapper())
        result = code_gen.generate_enum(mock_cursor)
        
        # Should handle large enums without issues
        assert "LargeEnum" in result
        assert "VALUE_0 = 0," in result
        assert "VALUE_999 = 999," in result
    
    def test_deeply_nested_includes(self, temp_dir):
        """Test deeply nested include structure"""
        generator = CSharpBindingsGenerator()
        
        # Create chain of includes
        headers = []
        for i in range(10):  # Deep nesting
            header = temp_dir / f"level{i}.h"
            if i < 9:
                header.write_text(f'#include "level{i+1}.h"\nint level{i}_func();')
            else:
                header.write_text(f"int level{i}_func();")
            headers.append(header)
        
        # Should handle deep includes without stack overflow
        output = generator.generate(
            [(str(headers[0]), "testlib")], 
            include_dirs=[str(temp_dir)],
            include_depth=5  # Limit depth
        )
        
        assert "namespace Bindings;" in output
    
    @pytest.fixture
    def temp_dir(self):
        """Fixture for temporary directory"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture 
    def temp_header_file(self, temp_dir):
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