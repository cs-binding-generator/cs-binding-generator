"""Tests for flag enum feature"""

import pytest
from pathlib import Path
from cs_binding_generator.config import parse_config_file
from cs_binding_generator.generator import CSharpBindingsGenerator


class TestFlagEnumsXMLParsing:
    """Test parsing of flags elements from XML configuration"""

    def test_parse_single_flag_enum(self, tmp_path):
        """Test parsing a single flag enum pattern"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <flags pattern="MyFlags"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.flag_enums) == 1
        assert config.flag_enums[0] == ("MyFlags", False)

    def test_parse_regex_flag_enum(self, tmp_path):
        """Test parsing a regex flag enum pattern"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <flags pattern="(.*)Flags" regex="true"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.flag_enums) == 1
        assert config.flag_enums[0] == ("(.*)Flags", True)

    def test_parse_multiple_flag_enums(self, tmp_path):
        """Test parsing multiple flag enum patterns"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <flags pattern="SpecificFlags"/>
    <flags pattern="(.*)Flags" regex="true"/>
    <flags pattern="Options"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.flag_enums) == 3
        assert config.flag_enums[0] == ("SpecificFlags", False)
        assert config.flag_enums[1] == ("(.*)Flags", True)
        assert config.flag_enums[2] == ("Options", False)

    def test_flag_enum_missing_pattern_raises_error(self, tmp_path):
        """Test that missing pattern attribute raises error"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <flags regex="true"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        with pytest.raises(ValueError, match="Flags element missing 'pattern' attribute"):
            parse_config_file(str(config_file))


class TestFlagEnumsCodeGeneration:
    """Test that flag enums are generated with [Flags] attribute"""

    def test_exact_match_flag_enum(self, temp_dir):
        """Test that exact match adds [Flags] attribute"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef enum {
                FLAG_A = 1,
                FLAG_B = 2,
                FLAG_C = 4
            } MyFlags;
            
            typedef enum {
                VALUE_A = 0,
                VALUE_B = 1
            } MyEnum;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <flags pattern="MyFlags"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.flag_enums:
            generator.type_mapper.add_flag_enum(pattern, is_regex)
        
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        output = result["testlib.cs"]
        
        # MyFlags should have [Flags] attribute
        assert "[Flags]" in output
        assert "[Flags]\npublic enum MyFlags" in output
        
        # MyEnum should NOT have [Flags] attribute
        lines = output.split('\n')
        for i, line in enumerate(lines):
            if 'enum MyEnum' in line:
                # Check that the previous line is not [Flags]
                assert i == 0 or '[Flags]' not in lines[i-1]

    def test_regex_flag_enum(self, temp_dir):
        """Test that regex pattern adds [Flags] attribute"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef enum {
                WINDOW_FULLSCREEN = 1,
                WINDOW_RESIZABLE = 2
            } WindowFlags;
            
            typedef enum {
                RENDER_VSYNC = 1,
                RENDER_HARDWARE = 2
            } RenderFlags;
            
            typedef enum {
                OPTION_A = 0,
                OPTION_B = 1
            } Options;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <flags pattern="(.*)Flags" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.flag_enums:
            generator.type_mapper.add_flag_enum(pattern, is_regex)
        
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        output = result["testlib.cs"]
        
        # Both *Flags enums should have [Flags] attribute
        assert output.count("[Flags]") == 2
        assert "[Flags]\npublic enum WindowFlags" in output
        assert "[Flags]\npublic enum RenderFlags" in output
        
        # Options should NOT have [Flags] attribute
        lines = output.split('\n')
        for i, line in enumerate(lines):
            if 'enum Options' in line:
                # Check that the previous line is not [Flags]
                assert i == 0 or '[Flags]' not in lines[i-1]

    def test_multiple_flag_patterns(self, temp_dir):
        """Test multiple flag patterns (first match wins)"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef enum {
                PERM_READ = 1,
                PERM_WRITE = 2
            } Permissions;
            
            typedef enum {
                MODE_A = 1,
                MODE_B = 2
            } FileMode;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <flags pattern="Permissions"/>
                <flags pattern="(.*)Mode" regex="true"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for pattern, is_regex in config.flag_enums:
            generator.type_mapper.add_flag_enum(pattern, is_regex)
        
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        output = result["testlib.cs"]
        
        # Both should have [Flags] attribute
        assert output.count("[Flags]") == 2
        assert "[Flags]\npublic enum Permissions" in output
        assert "[Flags]\npublic enum FileMode" in output

    def test_flag_enum_with_rename(self, temp_dir):
        """Test that flag enum works after rename"""
        header = temp_dir / "test.h"
        header.write_text("""
            typedef enum {
                SDL_WINDOW_FULLSCREEN = 1,
                SDL_WINDOW_RESIZABLE = 2
            } SDL_WindowFlags;
        """)

        config = temp_dir / "config.xml"
        config.write_text(f"""
            <bindings>
                <rename from="SDL_WindowFlags" to="WindowFlags"/>
                <flags pattern="WindowFlags"/>
                <library name="testlib" namespace="Test">
                    <include file="{header}"/>
                </library>
            </bindings>
        """)

        config = parse_config_file(str(config))
        
        generator = CSharpBindingsGenerator()
        for from_name, to_name, is_regex in config.renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
        for pattern, is_regex in config.flag_enums:
            generator.type_mapper.add_flag_enum(pattern, is_regex)
        
        result = generator.generate(
            config.header_library_pairs,
            output=str(temp_dir),
            library_namespaces=config.library_namespaces,
            include_dirs=[str(temp_dir)]
        )

        output = result["testlib.cs"]
        
        # Should have [Flags] on the renamed enum
        assert "[Flags]\npublic enum WindowFlags" in output
