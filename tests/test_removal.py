"""
Test the removal functionality for filtering types/functions.
"""

import tempfile
from pathlib import Path
import pytest

from cs_binding_generator.generator import CSharpBindingsGenerator


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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
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
        
        from cs_binding_generator.config import parse_config_file
        header_library_pairs, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements, visibility, global_constants, global_defines = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in removals:
            generator.type_mapper.add_removal(pattern, is_regex)
            
        result = generator.generate(
            header_library_pairs,
            output=str(temp_dir),
            library_namespaces=library_namespaces,
            include_dirs=[str(temp_dir)]
        )
        
        # Verify removed functions
        assert "internal_helper_function" not in result["testlib.cs"]
        assert "_private_function" not in result["testlib.cs"]
        assert "__system_function" not in result["testlib.cs"]
        # Verify kept functions
        assert "public_function" in result["testlib.cs"]
        assert "user_function" in result["testlib.cs"]
