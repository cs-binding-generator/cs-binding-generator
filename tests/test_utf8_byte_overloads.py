"""Tests for the opt-in byte*-param overload feature.

When ``<utf8-byte-overloads/>`` is present in the XML config, every non-variadic
function whose primary `[LibraryImport]` has at least one ``string?`` parameter
gets a parallel partial method with each of those parameters retyped as ``byte*``.
Lets callers hand pre-encoded UTF-8 buffers (u8 literals, pinned spans) to the
native side without re-encoding through a managed string.
"""

import pytest
from pathlib import Path

from cs_binding_generator.config import parse_config_file
from cs_binding_generator.generator import CSharpBindingsGenerator


class TestUtf8ByteOverloadsXMLParsing:
    """The XML config exposes the feature as a presence-only ``<utf8-byte-overloads/>``."""

    def test_presence_sets_flag(self, tmp_path):
        config_file = tmp_path / "cfg.xml"
        config_file.write_text(
            """
            <bindings>
                <utf8-byte-overloads/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        config = parse_config_file(str(config_file))
        assert config.utf8_byte_overloads is True

    def test_absence_keeps_default(self, tmp_path):
        config_file = tmp_path / "cfg.xml"
        config_file.write_text(
            """
            <bindings>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        config = parse_config_file(str(config_file))
        assert config.utf8_byte_overloads is False


class TestUtf8ByteOverloadsEmit:
    """End-to-end checks against the generated `.cs`."""

    def _generate(self, tmp_path, header_src, *, opt_in: bool):
        """Helper: produce a one-library binding from `header_src`."""
        header = tmp_path / "test.h"
        header.write_text(header_src)
        opt_in_xml = "<utf8-byte-overloads/>" if opt_in else ""
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                {opt_in_xml}
                <library name="testlib" namespace="Test" class="Native">
                    <include file="{header}"/>
                </library>
            </bindings>
            """
        )
        config = parse_config_file(str(config_xml))
        generator = CSharpBindingsGenerator()
        result = generator.generate(
            config.header_library_pairs,
            output=str(tmp_path),
            include_dirs=[str(tmp_path)],
            library_namespaces=config.library_namespaces,
            library_class_names=config.library_class_names,
            utf8_byte_overloads=config.utf8_byte_overloads,
        )
        return result["testlib.cs"]

    def test_disabled_emits_only_primary(self, tmp_path):
        # Baseline: a function with a string? param produces ONLY the primary P/Invoke.
        header = """
            void log_message(const char* message);
        """
        output = self._generate(tmp_path, header, opt_in=False)
        # Primary present.
        assert "public static partial void log_message(string? message);" in output
        # No byte* overload.
        assert "byte* message" not in output

    def test_enabled_emits_byte_overload_for_single_string_param(self, tmp_path):
        header = """
            void log_message(const char* message);
        """
        output = self._generate(tmp_path, header, opt_in=True)
        # Primary still emitted.
        assert "public static partial void log_message(string? message);" in output
        # Plus a byte* overload.
        assert "public static partial void log_message(byte* message);" in output
        # Both reference the same native entry point.
        assert output.count('EntryPoint = "log_message"') == 2

    def test_enabled_swaps_every_string_param(self, tmp_path):
        # Two char* params should both become byte* in the overload.
        header = """
            int set_string_property(unsigned int props, const char* name, const char* value);
        """
        output = self._generate(tmp_path, header, opt_in=True)
        assert (
            "public static partial int set_string_property(uint props, string? name, string? value);"
            in output
        )
        assert (
            "public static partial int set_string_property(uint props, byte* name, byte* value);"
            in output
        )

    def test_enabled_preserves_non_string_params(self, tmp_path):
        # Non-string params should be passed through verbatim in the overload.
        header = """
            int frobnicate(int count, const char* label, float weight);
        """
        output = self._generate(tmp_path, header, opt_in=True)
        # The overload keeps `int count` and `float weight` intact.
        assert (
            "public static partial int frobnicate(int count, byte* label, float weight);"
            in output
        )

    def test_enabled_skips_functions_without_string_params(self, tmp_path):
        # Functions with no char* params get no overload — there's nothing to swap.
        header = """
            int add_numbers(int a, int b);
        """
        output = self._generate(tmp_path, header, opt_in=True)
        # Exactly one partial method declaration.
        assert output.count("public static partial int add_numbers") == 1

    def test_enabled_preserves_bool_marshalling_on_overload(self, tmp_path):
        # A bool param needs its MarshalAs attribute on BOTH the primary and the overload.
        header = """
            unsigned char set_flag(const char* name, _Bool enabled);
        """
        output = self._generate(tmp_path, header, opt_in=True)
        # The byte* overload also keeps `[MarshalAs(UnmanagedType.I1)] bool enabled`.
        assert (
            "public static partial byte set_flag(byte* name, "
            "[MarshalAs(UnmanagedType.I1)] bool enabled);"
        ) in output

    def test_enabled_does_not_duplicate_when_overload_already_unique(self, tmp_path):
        # Two unrelated functions, only one of which has a string param. Only that one
        # gets the overload.
        header = """
            void with_string(const char* s);
            int without_string(int x);
        """
        output = self._generate(tmp_path, header, opt_in=True)
        assert output.count("public static partial void with_string") == 2
        assert output.count("public static partial int without_string") == 1
