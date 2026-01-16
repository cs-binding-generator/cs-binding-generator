"""
Test the removal functionality for filtering types/functions.
"""

import tempfile
from pathlib import Path
import pytest

from cs_binding_generator.generator import CSharpBindingsGenerator
from cs_binding_generator.config import parse_config_file, BindingConfig


class TestRemovalFunctionality:
    """Test removal feature that filters out types/functions"""

    def test_simple_function_removal(self, temp_dir):
        """Test removing a specific function by exact name"""
        header = temp_dir / "test.h"
        header.write_text("""
            void keep_function();
            void remove_function();
            void another_keep();
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="remove_function"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify removed function is not present
        assert "remove_function" not in result["testlib.cs"]
        # Verify kept functions are present
        assert "keep_function" in result["testlib.cs"]
        assert "another_keep" in result["testlib.cs"]

    def test_regex_function_removal(self, temp_dir):
        """Test removing functions using regex pattern"""
        header = temp_dir / "test.h"
        header.write_text("""
            void SDL_Init();
            void SDL_Quit();
            void SDL_CreateWindow();
            void my_function();
            void another_function();
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_.*" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify SDL_ functions are removed
        assert "SDL_Init" not in result["testlib.cs"]
        assert "SDL_Quit" not in result["testlib.cs"]
        assert "SDL_CreateWindow" not in result["testlib.cs"]
        # Verify other functions remain
        assert "my_function" in result["testlib.cs"]
        assert "another_function" in result["testlib.cs"]

    def test_struct_removal(self, temp_dir):
        """Test removing struct definitions"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct KeepStruct {
                int x;
            } KeepStruct;
            
            typedef struct RemoveStruct {
                int y;
            } RemoveStruct;
            
            typedef struct AnotherKeep {
                int z;
            } AnotherKeep;
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="RemoveStruct"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify removed struct is not present
        assert "struct RemoveStruct" not in result["testlib.cs"]
        # Verify kept structs are present
        assert "struct KeepStruct" in result["testlib.cs"]
        assert "struct AnotherKeep" in result["testlib.cs"]

    def test_enum_removal(self, temp_dir):
        """Test removing enum definitions"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef enum KeepEnum {
                KEEP_A,
                KEEP_B
            } KeepEnum;
            
            typedef enum RemoveEnum {
                REMOVE_A,
                REMOVE_B
            } RemoveEnum;
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="RemoveEnum"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify removed enum is not present
        assert "enum RemoveEnum" not in result["testlib.cs"]
        assert "REMOVE_A" not in result["testlib.cs"]
        # Verify kept enum is present
        assert "enum KeepEnum" in result["testlib.cs"]
        assert "KEEP_A" in result["testlib.cs"]

    def test_union_removal(self, temp_dir):
        """Test removing union definitions"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef union KeepUnion {
                int i;
                float f;
            } KeepUnion;
            
            typedef union RemoveUnion {
                int x;
                double d;
            } RemoveUnion;
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="RemoveUnion"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify removed union is not present
        assert "RemoveUnion" not in result["testlib.cs"]
        # Verify kept union is present
        assert "KeepUnion" in result["testlib.cs"]

    def test_multiple_removal_rules(self, temp_dir):
        """Test multiple removal rules with precedence"""
        header = temp_dir / "test.h"
        header.write_text("""
            void SDL_Init();
            void SDL_Quit();
            void TCOD_Init();
            void TCOD_Quit();
            void my_function();
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_.*" regex="true"/>
                <remove pattern="TCOD_Quit"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify SDL_ functions are removed
        assert "SDL_Init" not in result["testlib.cs"]
        assert "SDL_Quit" not in result["testlib.cs"]
        # Verify specific TCOD_Quit is removed
        assert "TCOD_Quit" not in result["testlib.cs"]
        # Verify TCOD_Init remains (only Quit was specifically removed)
        assert "TCOD_Init" in result["testlib.cs"]
        # Verify my_function remains
        assert "my_function" in result["testlib.cs"]

    def test_removal_with_rename_precedence(self, temp_dir):
        """Test that removals work alongside renames with proper precedence"""
        header = temp_dir / "test.h"
        header.write_text("""
            void SDL_CreateWindow();
            void SDL_DestroyWindow();
            void SDL_Init();
        """)
        
        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_Init"/>
                <rename from="SDL_(.*)" to="$1" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)
        
        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in config.renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify SDL_Init is removed (removal happens before function generation)
        assert "SDL_Init" not in result["testlib.cs"]
        assert "Init" not in result or "InitWindow" in result  # Make sure it's not just renamed
        # Verify other functions are renamed
        assert "CreateWindow" in result["testlib.cs"]
        assert "DestroyWindow" in result["testlib.cs"]

    def test_regex_removal_complex_pattern(self, temp_dir):
        """Test complex regex patterns for removal"""
        header = temp_dir / "test.h"
        header.write_text("""
            void internal_helper_function();
            void _private_function();
            void __system_function();
            void public_function();
            void user_function();
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="(_|__).*" regex="true"/>
                <remove pattern=".*_helper_.*" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))

        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)

        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        # Verify removed functions
        assert "internal_helper_function" not in result["testlib.cs"]
        assert "_private_function" not in result["testlib.cs"]
        assert "__system_function" not in result["testlib.cs"]
        # Verify kept functions
        assert "public_function" in result["testlib.cs"]
        assert "user_function" in result["testlib.cs"]

    def test_opaque_typedef_removal(self, temp_dir):
        """Test that opaque typedefs (forward declarations) are removed when matching removal pattern.

        This tests the bug fix where opaque typedefs like 'typedef struct SDL_Window SDL_Window;'
        were generating empty partial structs even when SDL_Window was marked for removal.
        """
        header = temp_dir / "test.h"
        header.write_text("""
            // Opaque typedef - no struct definition, just forward declaration
            typedef struct SDL_Window SDL_Window;
            typedef struct SDL_Renderer SDL_Renderer;
            typedef struct KeepHandle KeepHandle;

            // Functions that use the types - these have their own names
            KeepHandle* create_handle();
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_.*" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))

        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)

        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        # Verify SDL opaque types are NOT generated as empty partial structs
        assert "partial struct SDL_Window" not in result["testlib.cs"]
        assert "partial struct SDL_Renderer" not in result["testlib.cs"]
        # Verify kept opaque type IS generated
        assert "partial struct KeepHandle" in result["testlib.cs"]
        # Verify kept function remains
        assert "create_handle" in result["testlib.cs"]

    def test_opaque_typedef_removal_with_rename(self, temp_dir):
        """Test that opaque typedefs are removed even when rename rules exist.

        This tests the scenario where types are both renamed and removed,
        ensuring the renamed version doesn't leak through as an empty struct.
        """
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct SDL_Window SDL_Window;
            typedef struct SDL_Surface SDL_Surface;
            typedef struct MyHandle MyHandle;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_.*" regex="true"/>
                <rename from="SDL_Window" to="WindowHandle"/>
                <rename from="SDL_Surface" to="SurfaceHandle"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))

        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in config.renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)

        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        # Verify original SDL types are not generated
        assert "partial struct SDL_Window" not in result["testlib.cs"]
        assert "partial struct SDL_Surface" not in result["testlib.cs"]
        # Verify renamed versions are also not generated (removal should take precedence)
        assert "partial struct WindowHandle" not in result["testlib.cs"]
        assert "partial struct SurfaceHandle" not in result["testlib.cs"]
        # Verify kept type is generated
        assert "partial struct MyHandle" in result["testlib.cs"]

    def test_forward_declaration_struct_removal(self, temp_dir):
        """Test removal of forward-declared structs (STRUCT_DECL without definition)."""
        header = temp_dir / "test.h"
        header.write_text("""
            // Forward declaration style
            struct SDL_Context;
            typedef struct SDL_Context SDL_Context;

            struct KeepContext;
            typedef struct KeepContext KeepContext;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_.*" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))

        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)

        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        # Verify SDL context struct is not generated as a partial struct
        assert "partial struct SDL_Context" not in result["testlib.cs"]
        # Verify kept context is generated
        assert "partial struct KeepContext" in result["testlib.cs"]

    def test_underlying_struct_name_removal(self, temp_dir):
        """Test removal when typedef has different name from underlying struct.

        Tests the case: typedef struct _InternalName PublicName;
        Both names should be checked against removal patterns.
        """
        header = temp_dir / "test.h"
        header.write_text("""
            // Underlying struct name differs from typedef name
            typedef struct _SDL_InternalWindow SDL_Window;
            typedef struct _KeepInternal KeepHandle;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_.*" regex="true"/>
                <remove pattern="_SDL_.*" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))

        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)

        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        # Verify both the typedef name and underlying name are not generated
        assert "SDL_Window" not in result["testlib.cs"]
        assert "_SDL_InternalWindow" not in result["testlib.cs"]
        # Verify kept types are generated
        assert "partial struct KeepHandle" in result["testlib.cs"]
        assert "partial struct _KeepInternal" in result["testlib.cs"]

    def test_opaque_type_not_registered_when_removed(self, temp_dir):
        """Test that removed opaque types are not registered in the type mapper.

        This ensures that removed types don't affect pointer type resolution
        for other types that reference them.
        """
        header = temp_dir / "test.h"
        header.write_text("""
            typedef struct SDL_Window SDL_Window;
            typedef struct KeepType KeepType;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <remove pattern="SDL_.*" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))

        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.removals:
            generator.type_mapper.add_removal(pattern, is_regex)

        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        # Verify SDL_Window is not in the opaque_types set
        assert "SDL_Window" not in generator.type_mapper.opaque_types
        # Verify KeepType is in the opaque_types set
        assert "KeepType" in generator.type_mapper.opaque_types
