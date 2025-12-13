"""
Test multi-file deduplication behavior to prevent regression of function filtering bug.
"""

import tempfile
from pathlib import Path
import pytest

from cs_binding_generator.generator import CSharpBindingsGenerator


class TestMultiFileDeduplication:
    """Test that multi-file generation properly handles function deduplication"""

    def test_shared_functions_included_in_both_libraries(self, temp_dir):
        """Test that functions shared between headers are included in both libraries"""
        # Create a shared header with common functions
        shared_header = temp_dir / "shared.h"
        shared_header.write_text("""
            int shared_function_1();
            int shared_function_2();
            typedef struct SharedStruct {
                int value;
            } SharedStruct;
        """)
        
        # Create lib1 header that includes shared.h
        lib1_header = temp_dir / "lib1.h"
        lib1_header.write_text(f"""
            #include "{shared_header}"
            int lib1_specific_function();
        """)
        
        # Create lib2 header that also includes shared.h
        lib2_header = temp_dir / "lib2.h"
        lib2_header.write_text(f"""
            #include "{shared_header}"
            int lib2_specific_function();
        """)

        generator = CSharpBindingsGenerator()
        
        # Generate multi-file bindings processing both libraries
        result = generator.generate([
            (str(lib1_header), "lib1"),
            (str(lib2_header), "lib2")
        ], multi_file=True, output=str(temp_dir), include_dirs=[str(temp_dir)])
        
        assert isinstance(result, dict)
        assert "lib1.cs" in result
        assert "lib2.cs" in result
        
        lib1_content = result["lib1.cs"]
        lib2_content = result["lib2.cs"]
        
        # Shared functions should appear in lib1 (processed first) due to global deduplication
        assert "shared_function_1" in lib1_content
        assert "shared_function_2" in lib1_content
        # Shared functions should NOT appear in lib2 (processed second)
        assert "shared_function_1" not in lib2_content
        assert "shared_function_2" not in lib2_content
        
        # Shared struct should appear in lib1 (processed first) due to global deduplication
        assert "SharedStruct" in lib1_content
        # Shared struct should NOT appear in lib2 (processed second)
        assert "SharedStruct" not in lib2_content
        
        # Each library should have its specific function
        assert "lib1_specific_function" in lib1_content
        assert "lib2_specific_function" in lib2_content
        
        # But library-specific functions should not cross over
        assert "lib1_specific_function" not in lib2_content
        assert "lib2_specific_function" not in lib1_content

    def test_single_vs_multi_file_function_parity(self, temp_dir):
        """Test that single-file and multi-file modes include the same functions for equivalent inputs"""
        # Create a header with various function types
        main_header = temp_dir / "main.h"
        main_header.write_text("""
            // Basic functions
            int basic_func();
            void void_func();
            
            // Math-style functions (similar to SDL math functions)
            double math_cos(double x);
            float math_cosf(float x);
            double math_sin(double x);
            
            // System-style functions
            int sys_compare(const void* a, const void* b);
            void* sys_alloc(size_t size);
            
            // Structs and enums
            typedef struct MainStruct {
                int value;
            } MainStruct;
            
            enum MainEnum {
                MAIN_ENUM_VALUE1,
                MAIN_ENUM_VALUE2
            };
        """)
        
        # Create a dummy secondary header for multi-file mode
        dummy_header = temp_dir / "dummy.h"  
        dummy_header.write_text("""
            int dummy_function();
        """)

        generator = CSharpBindingsGenerator()
        
        # Generate single-file bindings (only main header)
        single_result = generator.generate([
            (str(main_header), "main")
        ], namespace="Test", include_dirs=[str(temp_dir)])
        
        # Generate multi-file bindings (main + dummy)
        multi_result = generator.generate([
            (str(dummy_header), "dummy"),  # Process dummy first to simulate the original bug
            (str(main_header), "main")     # Process main second
        ], multi_file=True, output=str(temp_dir), namespace="Test", include_dirs=[str(temp_dir)])
        
        assert isinstance(multi_result, dict)
        assert "main.cs" in multi_result
        
        single_content = single_result
        multi_main_content = multi_result["main.cs"]
        
        # Extract function names from both outputs
        single_functions = self._extract_function_names(single_content)
        multi_functions = self._extract_function_names(multi_main_content)
        
        # The multi-file version should have all the same functions as single-file
        # (This test would have failed before the fix)
        missing_functions = single_functions - multi_functions
        assert not missing_functions, f"Multi-file mode missing functions: {missing_functions}"
        
        # Verify specific functions that were problematic
        for func in ["basic_func", "math_cos", "math_cosf", "math_sin", "sys_compare", "sys_alloc"]:
            assert func in multi_main_content, f"Function {func} missing from multi-file output"

    def test_function_deduplication_within_library(self, temp_dir):
        """Test that duplicate functions within the same library are properly deduplicated"""
        # Create headers that define the same function
        header1 = temp_dir / "dup1.h"
        header1.write_text("""
            int duplicate_function();
        """)
        
        header2 = temp_dir / "dup2.h" 
        header2.write_text("""
            int duplicate_function();  // Same function signature
            int unique_function();
        """)
        
        # Create a main header that includes both
        main_header = temp_dir / "main.h"
        main_header.write_text(f"""
            #include "{header1}"
            #include "{header2}"
        """)

        generator = CSharpBindingsGenerator()
        
        result = generator.generate([
            (str(main_header), "main")
        ], namespace="Test", include_dirs=[str(temp_dir)])
        
        # Count occurrences of the duplicate function
        duplicate_count = result.count("duplicate_function")
        
        # Should appear only once in the generated bindings (plus in comments/metadata)
        # Look for the actual function declaration
        import re
        function_declarations = re.findall(r'public static.*duplicate_function\s*\(', result)
        assert len(function_declarations) == 1, f"Expected 1 duplicate_function declaration, found {len(function_declarations)}"

    def _extract_function_names(self, content: str) -> set:
        """Extract function names from generated C# content"""
        import re
        # Look for LibraryImport function declarations
        pattern = r'public static partial \w+\s+(\w+)\s*\('
        matches = re.findall(pattern, content)
        return set(matches)

    def test_global_deduplication_prevents_duplicate_partial_methods(self, temp_dir):
        """Test that global deduplication prevents duplicate partial method definitions"""
        # Create a shared header with functions that would cause conflicts
        shared_header = temp_dir / "shared.h"
        shared_header.write_text("""
            int shared_function();
            typedef struct SharedStruct {
                int value;
            } SharedStruct;
            typedef union SharedUnion {
                int i;
                float f;
            } SharedUnion;
        """)
        
        # Create two library headers that both include the shared header
        lib1_header = temp_dir / "lib1.h"
        lib1_header.write_text(f"""
            #include "{shared_header}"
            int lib1_function();
        """)
        
        lib2_header = temp_dir / "lib2.h"
        lib2_header.write_text(f"""
            #include "{shared_header}"
            int lib2_function();
        """)
        
        generator = CSharpBindingsGenerator()
        
        # Test multi-file generation
        result = generator.generate([
            (str(lib1_header), "lib1"),
            (str(lib2_header), "lib2")
        ], multi_file=True, output=str(temp_dir), include_dirs=[str(temp_dir)])
        
        lib1_content = result["lib1.cs"]
        lib2_content = result["lib2.cs"]
        
        # Count occurrences of shared items across both files
        combined_content = lib1_content + "\n" + lib2_content
        
        # With global deduplication in multi-file mode, shared functions appear only in lib1 (processed first)
        assert lib1_content.count("shared_function") >= 1
        assert lib2_content.count("shared_function") == 0
        
        # Structs also use global deduplication - each should appear only once total
        struct_count = combined_content.count("partial struct SharedStruct")
        union_count = combined_content.count("partial struct SharedUnion")
        
        # In global deduplication, structs/unions appear only once across all files
        assert struct_count == 1, f"Expected SharedStruct to appear once, found {struct_count}"
        assert union_count == 1, f"Expected SharedUnion to appear once, found {union_count}"

    def test_multi_file_with_renames_deduplication(self, temp_dir):
        """Test that multi-file generation with renames maintains proper deduplication"""
        shared_header = temp_dir / "shared.h"
        shared_header.write_text("""
            typedef struct SDL_Window SDL_Window;
            typedef struct TCOD_Console TCOD_Console;
            SDL_Window* SDL_CreateWindow();
            TCOD_Console* TCOD_console_new();
        """)
        
        lib1_header = temp_dir / "lib1.h"
        lib1_header.write_text(f"""
            #include "{shared_header}"
            int lib1_function(SDL_Window* win, TCOD_Console* con);
        """)
        
        lib2_header = temp_dir / "lib2.h"
        lib2_header.write_text(f"""
            #include "{shared_header}"
            int lib2_function(SDL_Window* win, TCOD_Console* con);
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_Window" to="Window"/>
                <rename from="TCOD_Console" to="Console"/>
                <rename from="SDL_CreateWindow" to="CreateWindow"/>
                <rename from="TCOD_console_new" to="ConsoleNew"/>
                <library name="lib1">
                    <namespace name="Test"/>
                    <include file="{lib1_header}"/>
                </library>
                <library name="lib2">
                    <namespace name="Test"/>
                    <include file="{lib2_header}"/>
                </library>
            </bindings>
        """)
        
        from cs_binding_generator.main import parse_config_file
        header_library_pairs, namespace, include_dirs, renames, removals, library_class_names = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            multi_file=True,
            output=str(temp_dir),
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        lib1_content = result["lib1.cs"]
        lib2_content = result["lib2.cs"]
        combined_content = lib1_content + "\n" + lib2_content
        
        # Verify renames are applied consistently
        assert "Window*" in lib1_content and "Window*" in lib2_content
        assert "Console*" in lib1_content and "Console*" in lib2_content
        assert "SDL_Window*" not in combined_content
        assert "TCOD_Console*" not in combined_content
        
        # Verify global deduplication - structs appear only once total
        window_struct_count = combined_content.count("partial struct Window")
        console_struct_count = combined_content.count("partial struct Console")
        
        assert window_struct_count <= 1, f"Window struct should appear at most once, found {window_struct_count}"
        assert console_struct_count <= 1, f"Console struct should appear at most once, found {console_struct_count}"