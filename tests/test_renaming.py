"""
Test renaming functionality for functions and types.
"""

import tempfile
from pathlib import Path
import pytest

from cs_binding_generator.main import parse_config_file
from cs_binding_generator.generator import CSharpBindingsGenerator


class TestRenamingFunctionality:
    """Test that renaming works for functions and types"""

    def test_function_renaming(self, temp_dir):
        """Test that function names can be renamed"""
        # Create a test header
        header = temp_dir / "test.h"
        header.write_text("""
            int SDL_CreateWindow();
            void SDL_DestroyWindow();
        """)
        
        # Create XML config with renames
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_CreateWindow" to="CreateWindow"/>
                <rename from="SDL_DestroyWindow" to="DestroyWindow"/>
                <library name="testlib">
                    <namespace name="Test"/>
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        # Parse config and generate bindings
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        # Verify renamed functions appear in output
        assert "CreateWindow" in result
        assert "DestroyWindow" in result
        
        # Verify EntryPoint still uses original names
        assert 'EntryPoint = "SDL_CreateWindow"' in result
        assert 'EntryPoint = "SDL_DestroyWindow"' in result
        
        # Verify method names are renamed (not in method declarations)
        assert "public static partial int CreateWindow()" in result
        assert "public static partial void DestroyWindow()" in result

    def test_type_renaming(self, temp_dir):
        """Test that type names can be renamed"""
        # Create a test header
        header = temp_dir / "test.h"
        header.write_text("""
            typedef enum SDL_BlendMode {
                SDL_BLENDMODE_NONE,
                SDL_BLENDMODE_BLEND
            } SDL_BlendMode;
            
            typedef struct SDL_Window {
                int width;
                int height;
            } SDL_Window;
            
            SDL_Window* SDL_GetWindow(SDL_BlendMode mode);
        """)
        
        # Create XML config with type renames
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_BlendMode" to="BlendMode"/>
                <rename from="SDL_Window" to="Window"/>
                <rename from="SDL_GetWindow" to="GetWindow"/>
                <library name="testlib">
                    <namespace name="Test"/>
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        # Parse config and generate bindings
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        # Verify renamed types appear in output
        assert "public enum BlendMode" in result
        assert "public unsafe partial struct Window" in result
        
        # Verify function parameters use renamed types
        assert "GetWindow(BlendMode mode)" in result
        
        # Verify EntryPoint uses original name
        assert 'EntryPoint = "SDL_GetWindow"' in result

    def test_multi_file_renaming_consistency(self, temp_dir):
        """Test that renames are applied consistently across multiple files"""
        # Create shared header
        shared_header = temp_dir / "shared.h"
        shared_header.write_text("""
            typedef enum SDL_Result {
                SDL_SUCCESS,
                SDL_FAILURE
            } SDL_Result;
        """)
        
        # Create lib1 header that uses shared types
        lib1_header = temp_dir / "lib1.h"
        lib1_header.write_text(f"""
            #include "{shared_header}"
            SDL_Result lib1_function();
        """)
        
        # Create lib2 header that also uses shared types
        lib2_header = temp_dir / "lib2.h"
        lib2_header.write_text(f"""
            #include "{shared_header}"
            SDL_Result lib2_function();
        """)
        
        # Create XML config with renames
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_Result" to="Result"/>
                <rename from="lib1_function" to="Lib1Function"/>
                <rename from="lib2_function" to="Lib2Function"/>
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
        
        # Parse config and generate multi-file bindings
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            namespace=namespace,
            include_dirs=[str(temp_dir)],
            multi_file=True,
            output=str(temp_dir)
        )
        
        # Verify both library files use the same renamed types
        assert isinstance(result, dict)
        assert "lib1.cs" in result
        assert "lib2.cs" in result
        
        lib1_content = result["lib1.cs"]
        lib2_content = result["lib2.cs"]
        
        # Both should use the renamed type
        assert "Result Lib1Function" in lib1_content
        assert "Result Lib2Function" in lib2_content
        
        # Verify the enum declaration uses renamed type
        assert "public enum Result" in lib1_content or "public enum Result" in lib2_content
        
        # Verify EntryPoints use original names
        assert 'EntryPoint = "lib1_function"' in lib1_content
        assert 'EntryPoint = "lib2_function"' in lib2_content

    def test_partial_renaming(self, temp_dir):
        """Test that only specified items are renamed, others remain unchanged"""
        # Create a test header
        header = temp_dir / "test.h"
        header.write_text("""
            int SDL_Function1();
            int SDL_Function2();
            int Other_Function();
        """)
        
        # Create XML config that only renames some functions
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_Function1" to="Function1"/>
                <!-- SDL_Function2 and Other_Function not renamed -->
                <library name="testlib">
                    <namespace name="Test"/>
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        # Parse config and generate bindings
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        # Verify only the specified function is renamed in method declarations
        assert "public static partial int Function1()" in result  # Renamed
        assert "public static partial int SDL_Function2()" in result  # Not renamed  
        assert "public static partial int Other_Function()" in result  # Not renamed
        
        # Verify EntryPoints use original names
        assert 'EntryPoint = "SDL_Function1"' in result

    def test_struct_pointer_renaming(self, temp_dir):
        """Test that struct pointer types are properly renamed"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct TCOD_Console TCOD_Console;
            TCOD_Console* TCOD_console_new(int w, int h);
            int TCOD_console_get_width(TCOD_Console* con);
            void TCOD_console_blit(TCOD_Console* src, TCOD_Console* dst);
            
            typedef struct {
                TCOD_Console* console;
                TCOD_Console** cache;
            } Context;
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="TCOD_Console" to="TCODConsole"/>
                <rename from="TCOD_console_new" to="ConsoleNew"/>
                <library name="testlib">
                    <namespace name="Test"/>
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        # Result is a string when not using multi_file=True
        output = result
        
        # Verify struct pointers are renamed in function signatures
        assert "TCODConsole*" in output
        assert "TCOD_Console*" not in output
        
        # Verify function return types are renamed
        assert "public static partial TCODConsole* ConsoleNew" in output
        
        # Verify double pointers are renamed
        assert "TCODConsole**" in output

    def test_multi_file_renaming_consistency(self, temp_dir):
        """Test that renames are applied consistently across multiple files"""
        # Create shared types
        shared_header = temp_dir / "shared.h"
        shared_header.write_text("""
            typedef struct SDL_Window SDL_Window;
            typedef struct TCOD_Console TCOD_Console;
        """)
        
        # Library 1 uses both types
        lib1_header = temp_dir / "lib1.h"
        lib1_header.write_text(f"""
            #include "{shared_header}"
            SDL_Window* SDL_CreateWindow();
            void TCOD_console_init(TCOD_Console* con);
        """)
        
        # Library 2 also uses both types
        lib2_header = temp_dir / "lib2.h"
        lib2_header.write_text(f"""
            #include "{shared_header}"
            void SDL_DestroyWindow(SDL_Window* win);
            TCOD_Console* TCOD_console_new();
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_Window" to="Window"/>
                <rename from="SDL_CreateWindow" to="CreateWindow"/>
                <rename from="SDL_DestroyWindow" to="DestroyWindow"/>
                <rename from="TCOD_Console" to="Console"/>
                <rename from="TCOD_console_new" to="ConsoleNew"/>
                <rename from="TCOD_console_init" to="ConsoleInit"/>
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
        
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
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
        
        lib1_output = result["lib1.cs"]
        lib2_output = result["lib2.cs"]
        
        # Verify renames are consistently applied in both files
        assert "Window*" in lib1_output and "Window*" in lib2_output
        assert "Console*" in lib1_output and "Console*" in lib2_output
        
        # Verify original names are not present as types
        assert "SDL_Window*" not in lib1_output and "SDL_Window*" not in lib2_output
        assert "TCOD_Console*" not in lib1_output and "TCOD_Console*" not in lib2_output

    def test_post_processing_safety_net(self, temp_dir):
        """Test that post-processing catches any missed renames"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct TestType TestType;
            TestType* test_function(TestType* param);
            typedef struct {
                TestType* field;
            } Container;
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="TestType" to="RenamedType"/>
                <library name="testlib">
                    <namespace name="Test"/>
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        # In single-file mode, result is a string, not a dictionary
        output = result
        
        # Verify post-processing worked - all references should be renamed
        assert "RenamedType*" in output
        assert "TestType*" not in output

    def test_entrypoint_preservation(self, temp_dir):
        """Test that EntryPoint attributes preserve original function names"""
        header = temp_dir / "test.h"
        header.write_text("""
            int SDL_CreateWindow();
            void SDL_DestroyWindow();
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_CreateWindow" to="CreateWindow"/>
                <rename from="SDL_DestroyWindow" to="DestroyWindow"/>
                <library name="testlib">
                    <namespace name="Test"/>
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, namespace, include_dirs, renames, removals = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        # In single-file mode, result is a string, not a dictionary
        output = result
        
        # Verify EntryPoint preserves original names
        assert 'EntryPoint = "SDL_CreateWindow"' in output
        assert 'EntryPoint = "SDL_DestroyWindow"' in output
        
        # Verify method signatures use renamed names
        assert "public static partial int CreateWindow()" in output
        assert "public static partial void DestroyWindow()" in output