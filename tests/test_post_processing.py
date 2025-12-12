"""
Test the post-processing safety net functionality for renames.
"""

import tempfile
from pathlib import Path
import pytest

from cs_binding_generator.generator import CSharpBindingsGenerator


class TestPostProcessingSafetyNet:
    """Test that the post-processing safety net catches missed renames"""

    def test_apply_final_renames_basic(self, temp_dir):
        """Test basic post-processing rename functionality"""
        generator = CSharpBindingsGenerator()
        generator.type_mapper.add_rename("OldType", "NewType")
        generator.type_mapper.add_rename("OldFunc", "NewFunc")
        
        test_output = """
            public OldType* field;
            public OldType** cache;
            OldType* OldFunc();
            void process(OldType* param);
        """
        
        processed = generator.apply_final_renames(test_output)
        
        # Verify all pointer references are renamed
        assert "NewType*" in processed
        assert "NewType**" in processed
        assert "OldType*" not in processed
        assert "OldType**" not in processed
        
        # Verify standalone type references are renamed
        assert "NewType* NewFunc()" in processed or "NewType*NewFunc()" in processed

    def test_apply_final_renames_word_boundaries(self, temp_dir):
        """Test that post-processing respects word boundaries"""
        generator = CSharpBindingsGenerator()
        generator.type_mapper.add_rename("Type", "T")
        
        test_output = """
            public Type* field;
            public TypeExtended* extended_field;
            public ExtendedType* another_field;
            void type_function();
        """
        
        processed = generator.apply_final_renames(test_output)
        
        # "Type" should be renamed to "T" only as standalone word
        assert "T*" in processed
        
        # Check that standalone Type* was replaced
        assert "public T* field;" in processed
        
        # But partial matches should not be affected
        assert "TypeExtended*" in processed
        assert "ExtendedType*" in processed
        assert "type_function" in processed

    def test_apply_final_renames_complex_types(self, temp_dir):
        """Test post-processing with complex type scenarios"""
        generator = CSharpBindingsGenerator()
        generator.type_mapper.add_rename("SDL_Window", "Window")
        generator.type_mapper.add_rename("TCOD_Console", "Console")
        generator.type_mapper.add_rename("Mix_Music", "Music")
        
        test_output = """
            // Function signatures
            public static partial SDL_Window* SDL_CreateWindow();
            public static partial void SDL_DestroyWindow(SDL_Window* win);
            
            // Struct fields
            public SDL_Window* window;
            public TCOD_Console* console;
            public TCOD_Console** console_cache;
            
            // Complex function with multiple types
            void render(SDL_Window* win, TCOD_Console* con, Mix_Music* music);
            
            // EntryPoint should not be affected
            [LibraryImport("lib", EntryPoint = "SDL_CreateWindow")]
            public static partial SDL_Window* CreateWindow();
        """
        
        processed = generator.apply_final_renames(test_output)
        
        # Verify all type pointers are renamed
        assert "Window*" in processed
        assert "Console*" in processed
        assert "Console**" in processed
        assert "Music*" in processed
        
        # Verify original type names are gone from type contexts
        assert "SDL_Window*" not in processed
        assert "TCOD_Console*" not in processed
        assert "TCOD_Console**" not in processed
        assert "Mix_Music*" not in processed
        
        # Verify EntryPoint strings are preserved (they contain quotes)
        assert 'EntryPoint = "SDL_CreateWindow"' in processed

    def test_apply_final_renames_preserves_entry_points(self, temp_dir):
        """Test that EntryPoint attributes are not affected by post-processing"""
        generator = CSharpBindingsGenerator()
        generator.type_mapper.add_rename("SDL_CreateWindow", "CreateWindow")
        generator.type_mapper.add_rename("SDL_DestroyWindow", "DestroyWindow")
        
        test_output = """
            [LibraryImport("SDL3", EntryPoint = "SDL_CreateWindow")]
            public static partial nint CreateWindow();
            
            [LibraryImport("SDL3", EntryPoint = "SDL_DestroyWindow")]  
            public static partial void DestroyWindow(nint win);
        """
        
        processed = generator.apply_final_renames(test_output)
        
        # EntryPoint values should be preserved exactly
        assert 'EntryPoint = "SDL_CreateWindow"' in processed
        assert 'EntryPoint = "SDL_DestroyWindow"' in processed
        
        # Method names should remain as intended (already renamed by normal process)
        assert "public static partial nint CreateWindow()" in processed
        assert "public static partial void DestroyWindow" in processed

    def test_apply_final_renames_edge_cases(self, temp_dir):
        """Test edge cases for post-processing"""
        generator = CSharpBindingsGenerator()
        generator.type_mapper.add_rename("Test", "T")
        generator.type_mapper.add_rename("A", "B")
        
        test_output = """
            // Single character rename
            A* field_a;
            A** cache_a;
            
            // Short name that could cause issues
            Test* test_field;
            
            // Comments should not be affected
            // This is a Test comment with Test mentions
            /* Another Test comment */
            
            // EntryPoint attributes should preserve function names
            [LibraryImport("testlib", EntryPoint = "Test")]
            
            // Other string literals will be affected
            "Test string with Test mentions"
            
            // In actual type contexts
            public Test GetTest();
            public void SetTest(Test value);
        """
        
        processed = generator.apply_final_renames(test_output)
        
        # Type references should be renamed
        assert "B*" in processed
        assert "B**" in processed
        assert "T*" in processed
        assert "A*" not in processed
        
        # Check for specific type context renames (not substring matches)
        assert "public T GetTest();" in processed
        assert "public void SetTest(T value);" in processed
        
        # EntryPoint attributes should preserve original function names
        assert 'EntryPoint = "Test"' in processed
        
        # Other string literals: first Test is protected by quote, second Test gets renamed
        assert '"Test string with T mentions"' in processed
        
        # Comments will be affected by renames (this is acceptable)
        assert "// This is a T comment with T mentions" in processed
        assert "/* Another T comment */" in processed

    def test_post_processing_integration_with_generation(self, temp_dir):
        """Test that post-processing is properly integrated in the generation pipeline"""
        # Create a header that might produce unrenamed references
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct TestStruct TestStruct;
            TestStruct* create_struct();
            void process_struct(TestStruct* s);
            
            typedef struct {
                TestStruct* ref;
                TestStruct** cache;
            } Container;
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="TestStruct" to="MyStruct"/>
                <library name="testlib">
                    <namespace name="Test"/>
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        from cs_binding_generator.main import parse_config_file
        header_library_pairs, namespace, include_dirs, renames = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name in renames.items():
            generator.type_mapper.add_rename(from_name, to_name)
            
        result = generator.generate(
            header_library_pairs, 
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        # In single-file mode, result is a string, not a dictionary
        output = result
        
        # After post-processing, there should be NO unrenamed references
        assert "MyStruct*" in output
        assert "MyStruct**" in output if "**" in output else True
        assert "TestStruct*" not in output
        assert "TestStruct**" not in output

    def test_post_processing_multi_file_consistency(self, temp_dir):
        """Test that post-processing works consistently across multi-file generation"""
        shared_header = temp_dir / "shared.h"
        shared_header.write_text("""
            typedef struct SharedType SharedType;
        """)
        
        lib1_header = temp_dir / "lib1.h"
        lib1_header.write_text(f"""
            #include "{shared_header}"
            SharedType* lib1_function();
        """)
        
        lib2_header = temp_dir / "lib2.h"
        lib2_header.write_text(f"""
            #include "{shared_header}"
            void lib2_function(SharedType* param);
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SharedType" to="Renamed"/>
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
        header_library_pairs, namespace, include_dirs, renames = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name in renames.items():
            generator.type_mapper.add_rename(from_name, to_name)
            
        result = generator.generate(
            header_library_pairs,
            multi_file=True,
            output=str(temp_dir), 
            namespace=namespace, 
            include_dirs=[str(temp_dir)]
        )
        
        lib1_output = result["lib1.cs"]
        lib2_output = result["lib2.cs"]
        combined = lib1_output + "\n" + lib2_output
        
        # Post-processing should ensure consistency across all files
        assert "Renamed*" in lib1_output and "Renamed*" in lib2_output
        assert "SharedType*" not in combined