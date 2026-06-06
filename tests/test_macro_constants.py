"""Tests for the macro-constants extraction pipeline.

Covers three closely-related extractor features:

- C-style cast stripping, so values like ``((SDL_AudioDeviceID) 0xFFFFFFFFu)`` reduce to
  a numeric expression we can emit as a C# enum member.
- Recursive macro expansion, so values like ``SDL_BUTTON_MASK(SDL_BUTTON_LEFT)`` resolve
  through both function-like and object-like macros into the underlying numeric expression.
- String-literal constants mode (``type="string"``), which emits matching macros as
  ``ReadOnlySpan<byte>`` members of the library class instead of an enum.
"""

import pytest
from pathlib import Path

from cs_binding_generator.config import parse_config_file
from cs_binding_generator.generator import CSharpBindingsGenerator


# ---------------------------------------------------------------------------
# 1. C-style cast stripping
# ---------------------------------------------------------------------------


class TestStripCCasts:
    """Unit tests for the `_strip_c_casts` helper."""

    @pytest.fixture
    def generator(self):
        return CSharpBindingsGenerator()

    def test_strips_cast_with_outer_parens(self, generator):
        # The SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK shape.
        result = generator._strip_c_casts("((SDL_AudioDeviceID) 0xFFFFFFFFu)")
        assert result == "(0xFFFFFFFFu)"

    def test_strips_cast_without_outer_parens(self, generator):
        assert generator._strip_c_casts("(uint32_t)42") == "42"

    def test_strips_cast_in_front_of_paren(self, generator):
        assert generator._strip_c_casts("(MyType)(1 + 2)") == "(1 + 2)"

    def test_strips_nested_casts(self, generator):
        # Both casts are followed by a numeric token, so both should peel off.
        assert generator._strip_c_casts("((Outer)(Inner) 0xFF)") == "(0xFF)"

    def test_strips_multi_word_cast(self, generator):
        # `(unsigned int)` and `(long long)` are common in SDL headers.
        assert generator._strip_c_casts("(unsigned int)42") == "42"
        assert generator._strip_c_casts("((long long) 0x1000)") == "(0x1000)"
        assert generator._strip_c_casts("(const unsigned int)(1 << 5)") == "(1 << 5)"

    def test_keeps_parenthesized_number(self, generator):
        # `(1)` is NOT a cast — leading-letter requirement on the identifier skips it.
        assert generator._strip_c_casts("(1)") == "(1)"

    def test_keeps_cast_followed_by_identifier(self, generator):
        # `(name) + 1` is `name + 1`, not a cast: the `+` is not a numeric-token lookahead.
        assert generator._strip_c_casts("(name) + 1") == "(name) + 1"

    def test_keeps_pointer_cast(self, generator):
        # Pointer casts contain `*`, which falls outside the `\w` identifier; we don't
        # claim to strip these — and the numeric check would reject them anyway.
        assert generator._strip_c_casts("(int*)0") == "(int*)0"

    def test_no_op_on_plain_number(self, generator):
        assert generator._strip_c_casts("0xDEADBEEF") == "0xDEADBEEF"
        assert generator._strip_c_casts("(1 << 5)") == "(1 << 5)"


class TestCastedMacroEndToEnd:
    """End-to-end pipeline: header → XML constants → generated C#."""

    def test_audio_device_default_playback(self, tmp_path):
        # Exactly the SDL_audio.h shape we hit in real-world bindings.
        header = tmp_path / "casted.h"
        header.write_text(
            """
            typedef unsigned int SDL_AudioDeviceID;

            #define SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK  ((SDL_AudioDeviceID) 0xFFFFFFFFu)
            #define SDL_AUDIO_DEVICE_DEFAULT_RECORDING ((SDL_AudioDeviceID) 0xFFFFFFFEu)
            """
        )
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                <constants name="SDL_AudioDeviceDefault"
                           pattern="SDL_AUDIO_DEVICE_DEFAULT_.*"
                           type="uint"/>
                <library name="testlib" namespace="Test">
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
            global_constants=config.global_constants,
        )

        output = result["testlib.cs"]
        assert "public enum SDL_AudioDeviceDefault" in output
        # The `u` suffix is preserved in the stored value; C# accepts it inside an
        # unchecked numeric expression.
        assert "SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK = unchecked((uint)((0xFFFFFFFFu)))" in output
        assert "SDL_AUDIO_DEVICE_DEFAULT_RECORDING = unchecked((uint)((0xFFFFFFFEu)))" in output

    def test_cast_followed_by_paren_expression(self, tmp_path):
        header = tmp_path / "cast.h"
        header.write_text(
            """
            #define MY_CONST ((unsigned int) (1 << 5))
            """
        )
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                <constants name="MyConsts" pattern="MY_.*" type="uint"/>
                <library name="testlib" namespace="Test">
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
            global_constants=config.global_constants,
        )
        output = result["testlib.cs"]
        # Outer parens from the original define survive the cast strip; that's fine
        # because C# accepts redundant parens around a numeric expression.
        assert "MY_CONST = unchecked((uint)(((1 << 5))))" in output


# ---------------------------------------------------------------------------
# 2. Recursive macro expansion
# ---------------------------------------------------------------------------


class TestMacroExpansionHelpers:
    """Unit tests for the expansion plumbing."""

    @pytest.fixture
    def generator(self):
        return CSharpBindingsGenerator()

    def test_object_like_substitution(self, generator):
        macros = {"BASE": (None, "42")}
        assert generator._expand_macros("BASE + 1", macros) == "42 + 1"

    def test_transitive_substitution(self, generator):
        macros = {
            "BASE": (None, "42"),
            "MID": (None, "BASE"),
            "TOP": (None, "MID + 1"),
        }
        assert generator._expand_macros("TOP", macros) == "42 + 1"

    def test_function_like_substitution(self, generator):
        # SDL_BUTTON_MASK(X) shape.
        macros = {
            "MASK": (["X"], "(1u << ((X)-1))"),
        }
        assert generator._expand_macros("MASK(3)", macros) == "(1u << ((3)-1))"

    def test_function_like_with_macro_arg(self, generator):
        # Exactly the SDL_BUTTON_LMASK shape.
        macros = {
            "MASK": (["X"], "(1u << ((X)-1))"),
            "LEFT": (None, "1"),
        }
        assert generator._expand_macros("MASK(LEFT)", macros) == "(1u << ((1)-1))"

    def test_string_literal_is_not_expanded(self, generator):
        # Identifier-shaped text inside a quoted string must NOT be substituted.
        macros = {"BASE": (None, "42")}
        assert generator._expand_macros('"BASE"', macros) == '"BASE"'

    def test_self_referential_macro_terminates(self, generator):
        # `#define FOO FOO` would expand forever; the depth cap saves us.
        macros = {"FOO": (None, "FOO")}
        # Should return some value (likely "FOO" itself since substitution is a no-op
        # on the second pass) without hanging.
        assert generator._expand_macros("FOO", macros) == "FOO"

    def test_unknown_function_like_is_left_alone(self, generator):
        # Arity mismatches and unknown names pass through.
        macros = {"MASK": (["X"], "X")}
        assert generator._expand_macros("UNKNOWN(7)", {}) == "UNKNOWN(7)"
        assert generator._expand_macros("MASK(a, b)", macros) == "MASK(a, b)"

    def test_args_with_nested_parens_split_correctly(self, generator):
        # Commas inside `(a,b)` belong to a single argument, not two.
        assert generator._split_macro_args("a, (b, c), d") == ["a", "(b, c)", "d"]

    def test_args_empty_yields_empty_list(self, generator):
        assert generator._split_macro_args("") == []
        assert generator._split_macro_args("   ") == []


class TestMacroExpansionEndToEnd:
    """End-to-end pipeline tests for recursive expansion."""

    def test_sdl_button_mask_shape(self, tmp_path):
        # Exactly mirrors SDL_mouse.h: SDL_BUTTON_MASK function-like macro, integer
        # button constants, and the *MASK aliases that combine them.
        header = tmp_path / "buttons.h"
        header.write_text(
            """
            #define SDL_BUTTON_LEFT     1
            #define SDL_BUTTON_MIDDLE   2
            #define SDL_BUTTON_RIGHT    3
            #define SDL_BUTTON_MASK(X)  (1u << ((X)-1))
            #define SDL_BUTTON_LMASK    SDL_BUTTON_MASK(SDL_BUTTON_LEFT)
            #define SDL_BUTTON_MMASK    SDL_BUTTON_MASK(SDL_BUTTON_MIDDLE)
            #define SDL_BUTTON_RMASK    SDL_BUTTON_MASK(SDL_BUTTON_RIGHT)
            """
        )
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                <constants name="SDL_MouseButtonFlags"
                           pattern="SDL_BUTTON_.*MASK"
                           type="uint"
                           flags="true"/>
                <library name="testlib" namespace="Test">
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
            global_constants=config.global_constants,
        )
        output = result["testlib.cs"]
        # Function-like macro itself should NOT appear as an enum member.
        assert "SDL_BUTTON_MASK =" not in output
        # The *MASK aliases must each resolve through the function-like call.
        assert "[Flags]" in output
        assert "SDL_BUTTON_LMASK = unchecked((uint)((1u << ((1)-1))))" in output
        assert "SDL_BUTTON_MMASK = unchecked((uint)((1u << ((2)-1))))" in output
        assert "SDL_BUTTON_RMASK = unchecked((uint)((1u << ((3)-1))))" in output

    def test_expansion_with_unresolved_identifier_is_rejected(self, tmp_path):
        # When an identifier doesn't resolve, the post-expansion value still contains
        # bare letters and fails the numeric check, so the macro is silently skipped.
        header = tmp_path / "unresolved.h"
        header.write_text(
            """
            #define DANGLING SOME_OTHER_THING
            #define RESOLVED 5
            """
        )
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                <constants name="Mixed" pattern="(DANGLING|RESOLVED)" type="uint"/>
                <library name="testlib" namespace="Test">
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
            global_constants=config.global_constants,
        )
        output = result["testlib.cs"]
        assert "RESOLVED = unchecked((uint)(5))" in output
        assert "DANGLING" not in output


# ---------------------------------------------------------------------------
# 3. String constants mode
# ---------------------------------------------------------------------------


class TestStringMacroDetection:
    """Unit tests for the string-literal recognizer."""

    @pytest.fixture
    def generator(self):
        return CSharpBindingsGenerator()

    def test_plain_string(self, generator):
        assert generator._is_string_macro_value('"hello"') is True

    def test_empty_string(self, generator):
        assert generator._is_string_macro_value('""') is True

    def test_escaped_quote_inside(self, generator):
        assert generator._is_string_macro_value(r'"say \"hi\""') is True

    def test_rejects_numeric(self, generator):
        assert generator._is_string_macro_value("42") is False

    def test_rejects_unquoted_identifier(self, generator):
        assert generator._is_string_macro_value("hello") is False

    def test_rejects_concatenated_literals(self, generator):
        # `"a" "b"` is two literals — we don't try to fuse them.
        assert generator._is_string_macro_value('"a" "b"') is False

    def test_rejects_unterminated(self, generator):
        assert generator._is_string_macro_value('"oops') is False


class TestStringConstantsXMLParsing:
    """The `name=` attribute is required for numeric groups but optional for string."""

    def test_string_constants_without_name(self, tmp_path):
        config_xml = tmp_path / "cfg.xml"
        config_xml.write_text(
            """
            <bindings>
                <constants pattern="SDL_PROP_.*_STRING" type="string"/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        config = parse_config_file(str(config_xml))
        assert len(config.global_constants) == 1
        name, pattern, ctype, flags = config.global_constants[0]
        assert name == ""
        assert pattern == "SDL_PROP_.*_STRING"
        assert ctype == "string"
        assert flags is False

    def test_numeric_constants_still_require_name(self, tmp_path):
        config_xml = tmp_path / "cfg.xml"
        config_xml.write_text(
            """
            <bindings>
                <constants pattern="FOO_.*" type="uint"/>
                <library name="testlib">
                    <include file="/tmp/test.h"/>
                </library>
            </bindings>
            """
        )
        with pytest.raises(ValueError, match="Constants element missing 'name' attribute"):
            parse_config_file(str(config_xml))


class TestStringConstantsEndToEnd:
    """End-to-end: header → string constants → library class members."""

    def test_string_constants_emitted_into_library_class(self, tmp_path):
        # SDL_PROP_*_STRING shape: plain #define X "literal".
        header = tmp_path / "props.h"
        header.write_text(
            """
            #define SDL_PROP_GPU_SHADER_CREATE_NAME_STRING   "SDL.gpu.shader.create.name"
            #define SDL_PROP_GPU_TEXTURE_CREATE_NAME_STRING  "SDL.gpu.texture.create.name"
            #define UNRELATED_CONSTANT 42
            """
        )
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                <constants pattern="SDL_PROP_.*_STRING" type="string"/>
                <library name="testlib" namespace="Test" class="SDL">
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
            global_constants=config.global_constants,
        )
        output = result["testlib.cs"]
        # The two string macros land as ReadOnlySpan<byte> members on the SDL class.
        assert "public static unsafe partial class SDL" in output
        assert (
            'public static System.ReadOnlySpan<byte> '
            'SDL_PROP_GPU_SHADER_CREATE_NAME_STRING => '
            '"SDL.gpu.shader.create.name"u8;'
        ) in output
        assert (
            'public static System.ReadOnlySpan<byte> '
            'SDL_PROP_GPU_TEXTURE_CREATE_NAME_STRING => '
            '"SDL.gpu.texture.create.name"u8;'
        ) in output
        # No enum wrapper should be created for the string group.
        assert "public enum" not in output
        # Unrelated numeric macro must not leak in via the string pattern.
        assert "UNRELATED_CONSTANT" not in output

    def test_string_group_does_not_capture_numeric_macros(self, tmp_path):
        # Even when a numeric macro's name matches the string pattern, the value
        # is not a string literal, so it gets dropped.
        header = tmp_path / "mixed.h"
        header.write_text(
            """
            #define SDL_PROP_NUMERIC 42
            #define SDL_PROP_NAME    "the name"
            """
        )
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                <constants pattern="SDL_PROP_.*" type="string"/>
                <library name="testlib" namespace="Test" class="SDL">
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
            global_constants=config.global_constants,
        )
        output = result["testlib.cs"]
        assert "SDL_PROP_NAME" in output
        assert "SDL_PROP_NUMERIC" not in output

    def test_string_and_numeric_groups_coexist(self, tmp_path):
        # Two `<constants>` groups against the same header, one numeric and one string.
        # The kind filter must keep them from cross-pollinating.
        header = tmp_path / "both.h"
        header.write_text(
            """
            #define MY_INT  42
            #define MY_STR  "hello"
            """
        )
        config_xml = tmp_path / "cs-bindings.xml"
        config_xml.write_text(
            f"""
            <bindings>
                <constants name="MyInts" pattern="MY_INT" type="uint"/>
                <constants pattern="MY_STR" type="string"/>
                <library name="testlib" namespace="Test" class="SDL">
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
            global_constants=config.global_constants,
        )
        output = result["testlib.cs"]
        # Numeric group becomes an enum.
        assert "public enum MyInts" in output
        assert "MY_INT = unchecked((uint)(42))" in output
        # String group becomes a class member.
        assert (
            'public static System.ReadOnlySpan<byte> MY_STR => "hello"u8;' in output
        )
