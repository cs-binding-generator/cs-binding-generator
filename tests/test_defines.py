"""Tests for compiler defines feature"""

import pytest
from cs_binding_generator.config import parse_config_file, BindingConfig
from cs_binding_generator.generator import CSharpBindingsGenerator


class TestDefinesXMLParsing:
    """Test parsing of define elements from XML configuration"""

    def test_parse_single_define_without_value(self, tmp_path):
        """Test parsing a single define without a value"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <define name="ENABLE_FEATURE"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.global_defines) == 1
        assert config.global_defines[0] == ("ENABLE_FEATURE", None)

    def test_parse_single_define_with_value(self, tmp_path):
        """Test parsing a single define with a value"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <define name="VERSION" value="123"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.global_defines) == 1
        assert config.global_defines[0] == ("VERSION", "123")

    def test_parse_multiple_defines(self, tmp_path):
        """Test parsing multiple defines"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <define name="ENABLE_FEATURE"/>
    <define name="VERSION" value="123"/>
    <define name="DEBUG"/>
    <define name="MAX_SIZE" value="1024"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.global_defines) == 4
        assert config.global_defines[0] == ("ENABLE_FEATURE", None)
        assert config.global_defines[1] == ("VERSION", "123")
        assert config.global_defines[2] == ("DEBUG", None)
        assert config.global_defines[3] == ("MAX_SIZE", "1024")

    def test_parse_no_defines(self, tmp_path):
        """Test parsing config with no defines"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.global_defines) == 0

    def test_define_missing_name_raises_error(self, tmp_path):
        """Test that define without name raises error"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <define value="123"/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        with pytest.raises(ValueError, match="Define element missing 'name' attribute"):
            parse_config_file(str(config_file))

    def test_define_with_empty_value(self, tmp_path):
        """Test parsing define with empty value attribute"""
        config_file = tmp_path / "config.xml"
        config_file.write_text("""
<bindings>
    <define name="EMPTY" value=""/>
    <library name="testlib">
        <include file="/tmp/test.h"/>
    </library>
</bindings>
        """)

        config = parse_config_file(str(config_file))

        assert len(config.global_defines) == 1
        assert config.global_defines[0] == ("EMPTY", "")


class TestDefinesCodeGeneration:
    """Test that defines are correctly applied during code generation"""

    def test_define_without_value_applied(self, temp_header_file, tmp_path):
        """Test that define without value generates -D flag"""
        header_content = """
#ifdef ENABLE_FEATURE
int feature_enabled() { return 1; }
#else
int feature_enabled() { return 0; }
#endif
        """
        from pathlib import Path
        Path(temp_header_file).write_text(header_content)

        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(temp_header_file, "testlib")],
            output=str(tmp_path),
            global_defines=[("ENABLE_FEATURE", None)],
        )

        # Should generate binding for feature_enabled function
        assert "feature_enabled" in result["testlib.cs"]

    def test_define_with_value_applied(self, temp_header_file, tmp_path):
        """Test that define with value generates -D flag with value"""
        header_content = """
#define VERSION_DEFAULT 0
#ifndef VERSION
#define VERSION VERSION_DEFAULT
#endif

int get_version() { return VERSION; }
        """
        from pathlib import Path
        Path(temp_header_file).write_text(header_content)

        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(temp_header_file, "testlib")],
            output=str(tmp_path),
            global_defines=[("VERSION", "42")],
        )

        # Should generate binding for get_version function
        assert "get_version" in result["testlib.cs"]

    def test_multiple_defines_applied(self, temp_header_file, tmp_path):
        """Test that multiple defines are all applied"""
        header_content = """
#if defined(FEATURE_A) && defined(FEATURE_B)
int both_features() { return 1; }
#endif

#ifdef FEATURE_A
int feature_a() { return 1; }
#endif

#ifdef FEATURE_B
int feature_b() { return 1; }
#endif
        """
        from pathlib import Path
        Path(temp_header_file).write_text(header_content)

        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(temp_header_file, "testlib")],
            output=str(tmp_path),
            global_defines=[("FEATURE_A", None), ("FEATURE_B", None)],
        )

        code = result["testlib.cs"]
        assert "both_features" in code
        assert "feature_a" in code
        assert "feature_b" in code

    def test_no_defines_default_behavior(self, temp_header_file, tmp_path):
        """Test that generation works without defines"""
        header_content = """
int simple_function() { return 0; }
        """
        from pathlib import Path
        Path(temp_header_file).write_text(header_content)

        generator = CSharpBindingsGenerator()
        result = generator.generate(
            [(temp_header_file, "testlib")],
            output=str(tmp_path),
            global_defines=[],
        )

        assert "simple_function" in result["testlib.cs"]

    def test_defines_apply_to_all_libraries(self, temp_header_file, tmp_path):
        """Test that global defines apply to all libraries"""
        import tempfile
        from pathlib import Path
        
        # Create two separate header files
        with tempfile.NamedTemporaryFile(mode='w', suffix='_lib1.h', delete=False) as f1:
            f1.write("""
#ifdef GLOBAL_FLAG
int lib1_function() { return 1; }
#endif
            """)
            header_file1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='_lib2.h', delete=False) as f2:
            f2.write("""
#ifdef GLOBAL_FLAG
int lib2_function() { return 2; }
#endif
            """)
            header_file2 = f2.name

        try:
            generator = CSharpBindingsGenerator()
            result = generator.generate(
                [(header_file1, "lib1"), (header_file2, "lib2")],
                output=str(tmp_path),
                global_defines=[("GLOBAL_FLAG", None)],
            )

            assert "lib1_function" in result["lib1.cs"]
            assert "lib2_function" in result["lib2.cs"]
        finally:
            import os
            os.unlink(header_file1)
            os.unlink(header_file2)

