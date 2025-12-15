"""
Tests for variadic function generation
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import clang.cindex

from cs_binding_generator.code_generators import CodeGenerator
from cs_binding_generator.generator import CSharpBindingsGenerator
from cs_binding_generator.type_mapper import TypeMapper


class TestVariadicFunctions:
    """Test variadic function generation"""

    def setup_method(self):
        self.type_mapper = TypeMapper()
        self.generator = CodeGenerator(self.type_mapper, "public", skip_variadic=False)

    def test_variadic_function_generates_with_dllimport_and_arglist(self):
        """Test that variadic functions use DllImport with __arglist"""
        mock_cursor = Mock()
        mock_cursor.spelling = "printf_like"
        mock_cursor.result_type.kind = clang.cindex.TypeKind.INT
        mock_cursor.result_type.spelling = "int"

        # Mock type to indicate variadic function
        mock_cursor.type.kind = clang.cindex.TypeKind.FUNCTIONPROTO
        mock_cursor.type.is_function_variadic.return_value = True

        # Mock parameter (format string)
        mock_param = Mock()
        mock_param.spelling = "format"
        mock_param.type.kind = clang.cindex.TypeKind.POINTER
        mock_param.type.spelling = "const char *"
        mock_pointee = Mock()
        mock_pointee.kind = clang.cindex.TypeKind.CHAR_S
        mock_param.type.get_pointee.return_value = mock_pointee

        mock_cursor.get_arguments.return_value = [mock_param]

        result = self.generator.generate_function(mock_cursor, "testlib")

        # Should contain DllImport (not LibraryImport)
        assert "DllImport" in result
        assert "LibraryImport" not in result

        # Should contain __arglist
        assert "__arglist" in result

        # Should have the function name
        assert "printf_like" in result

        # Should use extern (not partial)
        assert "extern" in result
        assert "partial" not in result

    def test_variadic_function_with_bool_return(self):
        """Test variadic function with bool return type"""
        mock_cursor = Mock()
        mock_cursor.spelling = "set_error"
        mock_cursor.result_type.kind = clang.cindex.TypeKind.BOOL
        mock_cursor.result_type.spelling = "_Bool"

        # Mock type to indicate variadic function
        mock_cursor.type.kind = clang.cindex.TypeKind.FUNCTIONPROTO
        mock_cursor.type.is_function_variadic.return_value = True

        # Mock parameter
        mock_param = Mock()
        mock_param.spelling = "fmt"
        mock_param.type.kind = clang.cindex.TypeKind.POINTER
        mock_param.type.spelling = "const char *"
        mock_pointee = Mock()
        mock_pointee.kind = clang.cindex.TypeKind.CHAR_S
        mock_param.type.get_pointee.return_value = mock_pointee

        mock_cursor.get_arguments.return_value = [mock_param]

        result = self.generator.generate_function(mock_cursor, "testlib")

        # Should have bool return type with marshalling
        assert "bool set_error" in result
        assert "MarshalAs(UnmanagedType.I1)" in result
        assert "__arglist" in result
        assert "DllImport" in result

    def test_non_variadic_function_uses_libraryimport(self):
        """Test that non-variadic functions still use LibraryImport"""
        mock_cursor = Mock()
        mock_cursor.spelling = "regular_func"
        mock_cursor.result_type.kind = clang.cindex.TypeKind.INT
        mock_cursor.result_type.spelling = "int"

        # Mock type to indicate NON-variadic function
        mock_cursor.type.kind = clang.cindex.TypeKind.FUNCTIONPROTO
        mock_cursor.type.is_function_variadic.return_value = False

        mock_cursor.get_arguments.return_value = []

        result = self.generator.generate_function(mock_cursor, "testlib")

        # Should contain LibraryImport (not DllImport)
        assert "LibraryImport" in result
        assert "DllImport" not in result

        # Should NOT contain __arglist
        assert "__arglist" not in result

        # Should use partial (not extern)
        assert "partial" in result
        assert "extern" not in result

    def test_skip_variadic_flag_skips_variadic_functions(self):
        """Test that skip_variadic flag prevents variadic function generation"""
        # Create generator with skip_variadic=True
        skip_generator = CodeGenerator(self.type_mapper, "public", skip_variadic=True)

        mock_cursor = Mock()
        mock_cursor.spelling = "printf_like"
        mock_cursor.result_type.kind = clang.cindex.TypeKind.INT
        mock_cursor.result_type.spelling = "int"

        # Mock type to indicate variadic function
        mock_cursor.type.kind = clang.cindex.TypeKind.FUNCTIONPROTO
        mock_cursor.type.is_function_variadic.return_value = True

        mock_param = Mock()
        mock_param.spelling = "format"
        mock_param.type.kind = clang.cindex.TypeKind.POINTER
        mock_param.type.get_pointee.return_value.kind = clang.cindex.TypeKind.CHAR_S

        mock_cursor.get_arguments.return_value = [mock_param]

        result = skip_generator.generate_function(mock_cursor, "testlib")

        # With the new behavior, skip_variadic drops the variadic arguments but
        # still generates the function as a normal (non-variadic) LibraryImport.
        assert result != ""
        assert "printf_like" in result
        assert "__arglist" not in result
        assert "LibraryImport" in result
        assert "partial" in result

    def test_skip_variadic_flag_does_not_skip_regular_functions(self):
        """Test that skip_variadic flag doesn't affect non-variadic functions"""
        # Create generator with skip_variadic=True
        skip_generator = CodeGenerator(self.type_mapper, "public", skip_variadic=True)

        mock_cursor = Mock()
        mock_cursor.spelling = "regular_func"
        mock_cursor.result_type.kind = clang.cindex.TypeKind.INT
        mock_cursor.result_type.spelling = "int"

        # Mock type to indicate NON-variadic function
        mock_cursor.type.kind = clang.cindex.TypeKind.FUNCTIONPROTO
        mock_cursor.type.is_function_variadic.return_value = False

        mock_cursor.get_arguments.return_value = []

        result = skip_generator.generate_function(mock_cursor, "testlib")

        # Should NOT be empty (not skipped)
        assert result != ""
        assert "regular_func" in result
        assert "LibraryImport" in result

    def test_variadic_function_no_helper_generated(self):
        """Test that helper functions are not generated for variadic functions"""
        mock_cursor = Mock()
        mock_cursor.spelling = "get_formatted_string"

        # Return char* (which normally gets a helper)
        mock_cursor.result_type.kind = clang.cindex.TypeKind.POINTER
        mock_cursor.result_type.spelling = "char *"
        mock_pointee = Mock()
        mock_pointee.kind = clang.cindex.TypeKind.CHAR_S
        mock_cursor.result_type.get_pointee.return_value = mock_pointee

        # Mock type to indicate variadic function
        mock_cursor.type.kind = clang.cindex.TypeKind.FUNCTIONPROTO
        mock_cursor.type.is_function_variadic.return_value = True

        mock_param = Mock()
        mock_param.spelling = "format"
        mock_param.type.kind = clang.cindex.TypeKind.POINTER
        mock_param.type.spelling = "const char *"
        mock_param_pointee = Mock()
        mock_param_pointee.kind = clang.cindex.TypeKind.CHAR_S
        mock_param.type.get_pointee.return_value = mock_param_pointee

        mock_cursor.get_arguments.return_value = [mock_param]

        result = self.generator.generate_function(mock_cursor, "testlib")

        # Should have the main function
        assert "get_formatted_string" in result

        # Should NOT have helper function (no "String" suffix)
        assert "get_formatted_stringString" not in result
        assert "MethodImpl" not in result

    def test_variadic_function_with_multiple_parameters(self):
        """Test variadic function with multiple fixed parameters before varargs"""
        mock_cursor = Mock()
        mock_cursor.spelling = "log_message"
        mock_cursor.result_type.kind = clang.cindex.TypeKind.VOID
        mock_cursor.result_type.spelling = "void"

        # Mock type to indicate variadic function
        mock_cursor.type.kind = clang.cindex.TypeKind.FUNCTIONPROTO
        mock_cursor.type.is_function_variadic.return_value = True

        # Mock two parameters
        mock_param1 = Mock()
        mock_param1.spelling = "level"
        mock_param1.type.kind = clang.cindex.TypeKind.INT
        mock_param1.type.spelling = "int"

        mock_param2 = Mock()
        mock_param2.spelling = "format"
        mock_param2.type.kind = clang.cindex.TypeKind.POINTER
        mock_param2.type.spelling = "const char *"
        mock_param2_pointee = Mock()
        mock_param2_pointee.kind = clang.cindex.TypeKind.CHAR_S
        mock_param2.type.get_pointee.return_value = mock_param2_pointee

        mock_cursor.get_arguments.return_value = [mock_param1, mock_param2]

        result = self.generator.generate_function(mock_cursor, "testlib")

        # Should have both parameters followed by __arglist
        assert "int level" in result
        assert "__arglist" in result

        # Should be after the parameters
        assert result.index("level") < result.index("__arglist")


class TestVariadicIntegration:
    """Integration tests for variadic functions with real headers"""

    def test_real_variadic_function_generation(self, temp_dir):
        """Test generating bindings from a real C header with variadic function"""
        # Create a test header with a variadic function
        header_content = """
#ifndef TEST_VARIADIC_H
#define TEST_VARIADIC_H

// Variadic function like printf
int my_printf(const char* format, ...);

// Non-variadic function for comparison
int regular_function(int x);

#endif
"""
        header_file = temp_dir / "test_variadic.h"
        header_file.write_text(header_content)

        # Generate bindings
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(str(header_file), "test")],
            output=str(temp_dir),
            skip_variadic=False,
        )

        # Check the generated file
        test_cs = temp_dir / "test.cs"
        assert test_cs.exists()
        content = test_cs.read_text()

        # Should have DllImport for variadic function
        assert "DllImport" in content
        assert "my_printf" in content
        assert "__arglist" in content

        # Should have LibraryImport for regular function
        assert "LibraryImport" in content
        assert "regular_function" in content

    def test_skip_variadic_integration(self, temp_dir):
        """Test --skip-variadic flag in integration"""
        # Create a test header with both types of functions
        header_content = """
#ifndef TEST_SKIP_H
#define TEST_SKIP_H

int my_printf(const char* format, ...);
int regular_function(int x);

#endif
"""
        header_file = temp_dir / "test_skip.h"
        header_file.write_text(header_content)

        # Generate bindings WITH skip_variadic=True
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(str(header_file), "test")],
            output=str(temp_dir),
            skip_variadic=True,
        )

        # Check the generated file
        test_cs = temp_dir / "test.cs"
        assert test_cs.exists()
        content = test_cs.read_text()

        # With the new behavior, skip_variadic drops the variadic args but
        # the function is still generated as a normal LibraryImport without __arglist.
        assert "my_printf" in content
        assert "__arglist" not in content

        # Should still have the regular function
        assert "regular_function" in content
        assert "LibraryImport" in content


class TestDisableRuntimeMarshallingWithVariadic:
    """Test DisableRuntimeMarshalling attribute behavior with variadic functions"""

    def test_bindings_without_variadic_has_disable_runtime_marshalling(self, temp_dir):
        """Test that bindings.cs has DisableRuntimeMarshalling when no variadic functions"""
        # Create a test header with NO variadic functions
        header_content = """
#ifndef TEST_NO_VARIADIC_H
#define TEST_NO_VARIADIC_H

int regular_function(int x);
void another_function(void);

#endif
"""
        header_file = temp_dir / "test_no_variadic.h"
        header_file.write_text(header_content)

        # Generate bindings
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(str(header_file), "test")],
            output=str(temp_dir),
            skip_variadic=False,
        )

        # Check bindings.cs
        bindings_cs = temp_dir / "bindings.cs"
        assert bindings_cs.exists()
        bindings_content = bindings_cs.read_text()

        # Should have DisableRuntimeMarshalling assembly attribute
        assert "[assembly: System.Runtime.CompilerServices.DisableRuntimeMarshalling]" in bindings_content

    def test_bindings_with_variadic_no_disable_runtime_marshalling(self, temp_dir):
        """Test that bindings.cs does NOT have DisableRuntimeMarshalling with variadic functions"""
        # Create a test header WITH variadic function
        header_content = """
#ifndef TEST_WITH_VARIADIC_H
#define TEST_WITH_VARIADIC_H

int my_printf(const char* format, ...);
int regular_function(int x);

#endif
"""
        header_file = temp_dir / "test_with_variadic.h"
        header_file.write_text(header_content)

        # Generate bindings
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(str(header_file), "test")],
            output=str(temp_dir),
            skip_variadic=False,
        )

        # Check bindings.cs
        bindings_cs = temp_dir / "bindings.cs"
        assert bindings_cs.exists()
        bindings_content = bindings_cs.read_text()

        # Should NOT have DisableRuntimeMarshalling assembly attribute
        assert "[assembly: System.Runtime.CompilerServices.DisableRuntimeMarshalling]" not in bindings_content

        # Should have the variadic function in test.cs
        test_cs = temp_dir / "test.cs"
        test_content = test_cs.read_text()
        assert "my_printf" in test_content
        assert "__arglist" in test_content

    def test_bindings_with_variadic_but_skip_flag_has_disable_runtime_marshalling(self, temp_dir):
        """Test that bindings.cs has DisableRuntimeMarshalling when variadic functions are skipped"""
        # Create a test header WITH variadic function
        header_content = """
#ifndef TEST_SKIP_VARIADIC_H
#define TEST_SKIP_VARIADIC_H

int my_printf(const char* format, ...);
int regular_function(int x);

#endif
"""
        header_file = temp_dir / "test_skip_variadic.h"
        header_file.write_text(header_content)

        # Generate bindings WITH skip_variadic=True
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(str(header_file), "test")],
            output=str(temp_dir),
            skip_variadic=True,
        )

        # Check bindings.cs
        bindings_cs = temp_dir / "bindings.cs"
        assert bindings_cs.exists()
        bindings_content = bindings_cs.read_text()

        # Should have DisableRuntimeMarshalling assembly attribute (because variadic was skipped)
        assert "[assembly: System.Runtime.CompilerServices.DisableRuntimeMarshalling]" in bindings_content

        # Under the new behavior, the variadic function is still generated
        # but without varargs; verify it is present and lacks __arglist.
        test_cs = temp_dir / "test.cs"
        test_content = test_cs.read_text()
        assert "my_printf" in test_content
        assert "__arglist" not in test_content

        # Should still have the regular function
        assert "regular_function" in test_content
