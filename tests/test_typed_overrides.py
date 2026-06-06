"""Tests for the `<typed-field>` and `<typed-param>` type-override elements.

Both let the XML config swap the auto-mapped C# type on a single struct field or
function parameter for whatever the user specifies — typically a `[Flags]` enum
extracted via `<constants>`, so call sites can write
``usage = MyFlags.X | MyFlags.Y`` instead of ``(uint)(MyFlags.X | MyFlags.Y)``.
"""

import pytest
from pathlib import Path

from cs_binding_generator.config import parse_config_file
from cs_binding_generator.generator import CSharpBindingsGenerator


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------


class TestTypedOverridesXMLParsing:
    """Both elements are keyed by the C identifier (pre-rename)."""

    def test_typed_field_is_parsed(self, tmp_path):
        config_file = tmp_path / "cfg.xml"
        config_file.write_text(
            """
            <bindings>
                <typed-field struct="MyStruct" field="usage" type="UsageFlags"/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        config = parse_config_file(str(config_file))
        assert config.typed_fields == {("MyStruct", "usage"): "UsageFlags"}

    def test_typed_param_is_parsed(self, tmp_path):
        config_file = tmp_path / "cfg.xml"
        config_file.write_text(
            """
            <bindings>
                <typed-param function="my_function" param="flags" type="MyFlags"/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        config = parse_config_file(str(config_file))
        assert config.typed_params == {("my_function", "flags"): "MyFlags"}

    def test_multiple_overrides_accumulate(self, tmp_path):
        config_file = tmp_path / "cfg.xml"
        config_file.write_text(
            """
            <bindings>
                <typed-field struct="A" field="x" type="EnumA"/>
                <typed-field struct="A" field="y" type="EnumB"/>
                <typed-field struct="B" field="x" type="EnumC"/>
                <typed-param function="f" param="p" type="EnumD"/>
                <typed-param function="g" param="q" type="EnumE"/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        config = parse_config_file(str(config_file))
        assert config.typed_fields == {
            ("A", "x"): "EnumA",
            ("A", "y"): "EnumB",
            ("B", "x"): "EnumC",
        }
        assert config.typed_params == {
            ("f", "p"): "EnumD",
            ("g", "q"): "EnumE",
        }

    def test_typed_field_missing_attr_errors(self, tmp_path):
        config_file = tmp_path / "cfg.xml"
        config_file.write_text(
            """
            <bindings>
                <typed-field struct="S" field="f"/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        with pytest.raises(ValueError, match="typed-field element missing"):
            parse_config_file(str(config_file))

    def test_typed_param_missing_attr_errors(self, tmp_path):
        config_file = tmp_path / "cfg.xml"
        config_file.write_text(
            """
            <bindings>
                <typed-param function="foo" type="Bar"/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        with pytest.raises(ValueError, match="typed-param element missing"):
            parse_config_file(str(config_file))


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


class TestTypedOverridesEmit:
    """End-to-end pipeline: header + XML override → expected C# substitution."""

    def _generate(self, tmp_path, header_src, config_xml):
        header = tmp_path / "test.h"
        header.write_text(header_src)
        config_file = tmp_path / "cs-bindings.xml"
        config_file.write_text(config_xml.format(header=str(header)))
        config = parse_config_file(str(config_file))
        generator = CSharpBindingsGenerator()
        # Wire renames the same way the CLI does — apply_rename relies on the
        # type_mapper carrying the rules, and `generate()` doesn't thread them
        # through on its own.
        for from_name, to_name, is_regex in config.renames:
            generator.type_mapper.add_rename(from_name, to_name, is_regex)
        result = generator.generate(
            config.header_library_pairs,
            output=str(tmp_path),
            include_dirs=[str(tmp_path)],
            library_namespaces=config.library_namespaces,
            library_class_names=config.library_class_names,
            global_constants=config.global_constants,
            utf8_byte_overloads=config.utf8_byte_overloads,
            typed_fields=config.typed_fields,
            typed_params=config.typed_params,
        )
        return result["testlib.cs"]

    def test_typed_field_retypes_struct_member(self, tmp_path):
        header = """
            typedef struct {
                unsigned int usage;
                unsigned int size;
            } BufferDesc;
        """
        config_xml = """
            <bindings>
                <typed-field struct="BufferDesc" field="usage" type="UsageFlags"/>
                <library name="testlib" namespace="Test" class="Native">
                    <include file="{header}"/>
                </library>
            </bindings>
        """
        output = self._generate(tmp_path, header, config_xml)
        # The matched field is retyped; the other field stays auto-mapped.
        assert "public UsageFlags usage;" in output
        assert "public uint size;" in output

    def test_typed_param_retypes_function_parameter(self, tmp_path):
        header = """
            int do_work(unsigned int flags, int count);
        """
        config_xml = """
            <bindings>
                <typed-param function="do_work" param="flags" type="WorkFlags"/>
                <library name="testlib" namespace="Test" class="Native">
                    <include file="{header}"/>
                </library>
            </bindings>
        """
        output = self._generate(tmp_path, header, config_xml)
        # `flags` becomes WorkFlags; `count` stays int.
        assert "public static partial int do_work(WorkFlags flags, int count);" in output

    def test_unmatched_field_is_untouched(self, tmp_path):
        # An override against a struct/field that doesn't exist is a no-op (it just
        # never fires); the rest of the binding generates normally.
        header = """
            typedef struct { unsigned int x; } S;
        """
        config_xml = """
            <bindings>
                <typed-field struct="OtherStruct" field="x" type="WontFire"/>
                <library name="testlib" namespace="Test" class="Native">
                    <include file="{header}"/>
                </library>
            </bindings>
        """
        output = self._generate(tmp_path, header, config_xml)
        assert "public uint x;" in output
        assert "WontFire" not in output

    def test_typed_param_uses_c_function_name(self, tmp_path):
        # The override key uses the C identifier, so renames don't break the match.
        header = """
            int sdl_do_thing(unsigned int flags);
        """
        config_xml = """
            <bindings>
                <rename from="sdl_(.*)" to="$1" regex="true"/>
                <typed-param function="sdl_do_thing" param="flags" type="ThingFlags"/>
                <library name="testlib" namespace="Test" class="Native">
                    <include file="{header}"/>
                </library>
            </bindings>
        """
        output = self._generate(tmp_path, header, config_xml)
        # The C# method got renamed to `do_thing`, but the typed-param still fires
        # because we keyed by the C name.
        assert "public static partial int do_thing(ThingFlags flags);" in output

    def test_typed_param_retypes_on_byte_overload_too(self, tmp_path):
        # When utf8-byte-overloads is on, the byte* overload also has to honor
        # typed-param. Otherwise the overload would emit raw `uint flags` while the
        # primary has the typed enum, and call sites that pass an enum value would
        # pick the wrong overload.
        header = """
            int do_work(unsigned int flags, const char* label);
        """
        config_xml = """
            <bindings>
                <utf8-byte-overloads/>
                <typed-param function="do_work" param="flags" type="WorkFlags"/>
                <library name="testlib" namespace="Test" class="Native">
                    <include file="{header}"/>
                </library>
            </bindings>
        """
        output = self._generate(tmp_path, header, config_xml)
        # Primary keeps the typed flags + string? label.
        assert (
            "public static partial int do_work(WorkFlags flags, string? label);"
            in output
        )
        # byte* overload also has the typed flags; only the string? swapped to byte*.
        assert (
            "public static partial int do_work(WorkFlags flags, byte* label);" in output
        )

    def test_typed_field_does_not_affect_other_structs(self, tmp_path):
        # Two structs both have a field named `flags`. The override targets only one.
        header = """
            typedef struct { unsigned int flags; } A;
            typedef struct { unsigned int flags; } B;
        """
        config_xml = """
            <bindings>
                <typed-field struct="A" field="flags" type="AFlags"/>
                <library name="testlib" namespace="Test" class="Native">
                    <include file="{header}"/>
                </library>
            </bindings>
        """
        output = self._generate(tmp_path, header, config_xml)
        # A.flags becomes AFlags.
        assert "public AFlags flags;" in output
        # B.flags stays uint.
        assert "public uint flags;" in output
