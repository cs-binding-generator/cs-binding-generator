"""
Test edge cases and regression tests for complex scenarios encountered during development.
"""

import tempfile
from pathlib import Path
import pytest

from cs_binding_generator.config import parse_config_file
from cs_binding_generator.generator import CSharpBindingsGenerator


class TestEdgeCases:
    """Test edge cases and complex scenarios"""

    def test_tcod_console_rename_edge_case(self, temp_dir):
        """Regression test for TCOD_Console rename issue where some references weren't renamed"""
        # This tests the exact scenario that caused the original bug:
        # - Multi-file generation
        # - Struct pointers in various contexts (return types, parameters, struct fields)
        # - Mixed renamed and non-renamed structs
        
        # Create LibTCOD-style headers
        console_header = temp_dir / "console.h"
        console_header.write_text("""
            typedef struct TCOD_Console TCOD_Console;
            typedef struct TCOD_ConsoleTile TCOD_ConsoleTile;  // Similar name, should NOT be renamed
            typedef struct TCOD_console_t TCOD_console_t;      // Different name, should NOT be renamed
            
            // Function return types
            TCOD_Console* TCOD_console_new(int w, int h);
            
            // Function parameters  
            int TCOD_console_get_width(TCOD_Console* con);
            void TCOD_console_blit(TCOD_Console* src, TCOD_Console* dst);
            
            // Const pointers
            void TCOD_console_print(const TCOD_Console* con, int x, int y, const char* text);
            
            // Struct fields with pointers
            typedef struct TCOD_ContextParams {
                TCOD_Console* console;
                TCOD_ConsoleTile* tiles;
            } TCOD_ContextParams;
            
            typedef struct TCOD_RendererSDL2 {
                TCOD_Console* cache_console;
                TCOD_Console** console_cache;
            } TCOD_RendererSDL2;
        """)
        
        # SDL3 header that also references TCOD types (multi-library scenario)
        sdl_header = temp_dir / "sdl.h"
        sdl_header.write_text(f"""
            #include "{console_header}"
            
            typedef struct SDL_Window SDL_Window;
            
            SDL_Window* SDL_CreateWindow();
            void SDL_DestroyWindow(SDL_Window* win);
            
            // Cross-library function using both types
            void SDL_RenderConsole(SDL_Window* win, TCOD_Console* con);
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="TCOD_Console" to="TCODConsole"/>
                <rename from="TCOD_console_new" to="ConsoleNew"/>
                <rename from="SDL_CreateWindow" to="CreateWindow"/>
                <library name="libtcod" namespace="LibTCOD">
                    <include file="{console_header}"/>
                </library>
                <library name="SDL3" namespace="SDL3">
                    <include file="{sdl_header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        libtcod_output = result["libtcod.cs"]
        sdl_output = result["SDL3.cs"]
        combined = libtcod_output + "\n" + sdl_output
        
        # Critical test: NO unrenamed TCOD_Console* should exist anywhere
        assert "TCOD_Console*" not in combined, "Found unrenamed TCOD_Console* reference"
        assert "const TCOD_Console*" not in combined, "Found unrenamed const TCOD_Console* reference"
        
        # Verify all references are properly renamed
        assert "TCODConsole*" in combined
        assert "TCODConsole**" in combined if "**" in combined else True
        
        # Verify function signatures use renamed types
        assert "public static partial TCODConsole* ConsoleNew" in libtcod_output
        assert "TCOD_console_get_width(TCODConsole* con)" in libtcod_output
        assert "TCOD_console_blit(TCODConsole* src, TCODConsole* dst)" in libtcod_output
        
        # Verify struct fields use renamed types
        assert "public TCODConsole* console;" in libtcod_output
        assert "public TCODConsole* cache_console;" in libtcod_output
        
        # Verify cross-library consistency
        assert "SDL_RenderConsole(SDL_Window* win, TCODConsole* con)" in sdl_output
        
        # Verify similar names are NOT renamed
        assert "TCOD_ConsoleTile" in combined  # Should remain unchanged
        assert "TCOD_console_t" in combined   # Should remain unchanged
        
        # Verify EntryPoint preservation
        assert 'EntryPoint = "TCOD_console_new"' in libtcod_output

    def test_elaborated_vs_record_type_consistency(self, temp_dir):
        """Test that ELABORATED and RECORD types are handled consistently"""
        header = temp_dir / "test.h"
        header.write_text("""
            // Forward declaration (ELABORATED type)
            typedef struct ForwardDeclared ForwardDeclared;
            
            // Full definition (RECORD type)
            typedef struct FullyDefined {
                int value;
                ForwardDeclared* forward_ref;
            } FullyDefined;
            
            // Functions using both
            ForwardDeclared* get_forward();
            FullyDefined* get_full();
            void process(ForwardDeclared* fwd, FullyDefined* full);
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="ForwardDeclared" to="Forward"/>
                <rename from="FullyDefined" to="Full"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            output=str(temp_dir),
            library_namespaces=library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # In multi-file mode, result is a dictionary
        output = result["testlib.cs"]
        
        # Both types should be consistently renamed regardless of ELABORATED vs RECORD
        assert "Forward*" in output
        assert "Full*" in output
        assert "ForwardDeclared*" not in output
        assert "FullyDefined*" not in output

    def test_post_processing_regex_safety(self, temp_dir):
        """Test that post-processing regex replacements are safe and don't cause false matches"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct Test Test;
            typedef struct TestExtended TestExtended;
            typedef struct ExtendedTest ExtendedTest;
            
            Test* get_test();
            TestExtended* get_test_extended();
            ExtendedTest* get_extended_test();
            
            // Function names containing the type name
            void test_function();
            void extended_test_function();
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="Test" to="T"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            output=str(temp_dir),
            library_namespaces=library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # In multi-file mode, result is a dictionary
        output = result["testlib.cs"]
        
        # "Test" should be renamed to "T" only as a standalone type, not as part of other names
        assert "T*" in output
        
        # Check that standalone Test* was replaced (look for the specific method signature)
        assert "public static partial T* get_test()" in output
        
        # But "TestExtended" and "ExtendedTest" should remain unchanged
        assert "TestExtended*" in output
        assert "ExtendedTest*" in output
        
        # Function names should not be affected by type renames
        assert "test_function" in output
        assert "extended_test_function" in output

    def test_complex_multi_library_scenario(self, temp_dir):
        """Test complex scenario with multiple libraries, shared types, and cross-references"""
        # Shared types header
        shared_header = temp_dir / "shared.h" 
        shared_header.write_text("""
            typedef struct SharedType SharedType;
            typedef struct AnotherSharedType AnotherSharedType;
        """)
        
        # Graphics library
        graphics_header = temp_dir / "graphics.h"
        graphics_header.write_text(f"""
            #include "{shared_header}"
            
            typedef struct GraphicsContext GraphicsContext;
            
            GraphicsContext* graphics_create();
            void graphics_render(GraphicsContext* ctx, SharedType* data);
            SharedType* graphics_get_data(GraphicsContext* ctx);
        """)
        
        # Audio library
        audio_header = temp_dir / "audio.h"
        audio_header.write_text(f"""
            #include "{shared_header}"
            
            typedef struct AudioContext AudioContext;
            
            AudioContext* audio_create();
            void audio_play(AudioContext* ctx, AnotherSharedType* data);
            void audio_mix(SharedType* input, AnotherSharedType* output);
        """)
        
        # Main library that uses both
        main_header = temp_dir / "main.h"
        main_header.write_text(f"""
            #include "{graphics_header}"
            #include "{audio_header}"
            
            typedef struct MainEngine MainEngine;
            
            MainEngine* main_create();
            void main_run(MainEngine* engine, GraphicsContext* gfx, AudioContext* audio);
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SharedType" to="Shared"/>
                <rename from="AnotherSharedType" to="AnotherShared"/>
                <rename from="GraphicsContext" to="GfxContext"/>
                <rename from="AudioContext" to="AudioCtx"/>
                <rename from="MainEngine" to="Engine"/>
                <rename from="graphics_create" to="CreateGraphics"/>
                <rename from="audio_create" to="CreateAudio"/>
                <rename from="main_create" to="CreateMain"/>
                <library name="graphics" namespace="Graphics">
                    <include file="{graphics_header}"/>
                </library>
                <library name="audio" namespace="Audio">
                    <include file="{audio_header}"/>
                </library>
                <library name="main" namespace="Main">
                    <include file="{main_header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        graphics_output = result["graphics.cs"]
        audio_output = result["audio.cs"]
        main_output = result["main.cs"]
        combined = graphics_output + "\n" + audio_output + "\n" + main_output
        
        # Verify all renames are applied consistently across all files
        assert "Shared*" in combined
        assert "AnotherShared*" in combined
        assert "GfxContext*" in combined
        assert "AudioCtx*" in combined
        assert "Engine*" in combined
        
        # Verify no original names remain as types
        assert "SharedType*" not in combined
        assert "AnotherSharedType*" not in combined
        assert "GraphicsContext*" not in combined
        assert "AudioContext*" not in combined
        assert "MainEngine*" not in combined
        
        # Verify function renames
        assert "CreateGraphics" in graphics_output
        assert "CreateAudio" in audio_output
        assert "CreateMain" in main_output
        
        # Verify cross-library type consistency
        assert "main_run(Engine* engine, GfxContext* gfx, AudioCtx* audio)" in main_output
        assert "graphics_render(GfxContext* ctx, Shared* data)" in graphics_output
        assert "audio_mix(Shared* input, AnotherShared* output)" in audio_output

    def test_opaque_vs_defined_struct_consistency(self, temp_dir):
        """Test that opaque and defined structs are renamed consistently"""
        header = temp_dir / "test.h"
        header.write_text("""
            // Opaque struct (forward declaration only)
            typedef struct OpaqueType OpaqueType;
            
            // Defined struct
            typedef struct DefinedType {
                int value;
                OpaqueType* opaque_ref;
            } DefinedType;
            
            // Functions using both
            OpaqueType* create_opaque();
            DefinedType* create_defined();
            void process_both(OpaqueType* opaque, DefinedType* defined);
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="OpaqueType" to="Opaque"/>
                <rename from="DefinedType" to="Defined"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            output=str(temp_dir),
            library_namespaces=library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # In multi-file mode, result is a dictionary
        output = result["testlib.cs"]
        
        # Both opaque and defined structs should be renamed consistently
        assert "Opaque*" in output
        assert "Defined*" in output
        assert "OpaqueType*" not in output
        assert "DefinedType*" not in output
        
        # Verify struct field references use renamed types
        assert "public Opaque* opaque_ref;" in output
        
        # Verify function signatures use renamed types
        assert "create_opaque()" in output
        assert "create_defined()" in output
        assert "process_both(Opaque* opaque, Defined* defined)" in output

    def test_typedef_chain_renaming(self, temp_dir):
        """Test renaming through typedef chains"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct BaseType BaseType;
            typedef BaseType AliasType;
            typedef AliasType* AliasPtr;
            
            AliasType* get_alias();
            AliasPtr get_alias_ptr();
            void process_alias(AliasType* alias, AliasPtr ptr);
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="BaseType" to="Base"/>
                <rename from="AliasType" to="Alias"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
            
        result = generator.generate(
            header_library_pairs, 
            output=str(temp_dir),
            library_namespaces=library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # In multi-file mode, result is a dictionary
        output = result["testlib.cs"]
        
        # Verify typedef chains resolve and apply renames correctly
        # AliasType -> Alias, but typedef resolves to BaseType -> Base
        assert "Base*" in output  # Typedef resolved to the base type
        assert "AliasType*" not in output  # Original name should not appear
        assert "BaseType*" not in output  # Original base type name should not appear
        assert "BaseType*" not in output
        assert "AliasType*" not in output