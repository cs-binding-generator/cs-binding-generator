import os
from cs_binding_generator.generator import CSharpBindingsGenerator


def test_generate_underlying_struct_for_typedef(tmp_path):
    # Create a small header that forward-declares an underlying struct
    # and typedefs it to an alias. Also reference both names in functions
    # to ensure the generator sees usages.
    header = tmp_path / "xlib_typedef.h"
    header.write_text(
        """
        struct _XDisplay;
        typedef struct _XDisplay Display;

        /* References to both names to simulate real headers */
        void XOpenDisplay(Display* d);
        void XCloseDisplay(_XDisplay* d);
        """
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    g = CSharpBindingsGenerator()
    # Generate bindings for our test header
    g.generate([(str(header), "testlib")], output=str(out_dir), include_dirs=[], ignore_missing=False)

    # Read generated file and assert both names were emitted as opaque structs
    generated = (out_dir / "testlib.cs").read_text()

    assert "partial struct _XDisplay" in generated
    assert "partial struct Display" in generated
