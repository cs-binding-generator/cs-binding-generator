"""
Main C# bindings generator orchestration
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional

import clang.cindex
from clang.cindex import CursorKind

from .code_generators import CodeGenerator, OutputBuilder
from .constants import DEFAULT_NAMESPACE, NATIVE_METHODS_CLASS
from .type_mapper import TypeMapper


class CSharpBindingsGenerator:
    """Main orchestrator for generating C# bindings from C headers"""

    def __init__(self):
        self.type_mapper = TypeMapper()
        self.code_generator = None  # Will be initialized with visibility setting
        self.visibility = "public"  # Default visibility

        # Store generated items by library
        self.generated_functions = {}  # library -> [functions]
        self.generated_structs = {}  # library -> [structs]
        self.generated_unions = {}  # library -> [unions]
        self.generated_enums = {}  # library -> [enums]
        self.source_file = None

        # Track what we've already generated to avoid duplicates
        self.seen_functions = set()  # (name, location)
        self.seen_structs = set()  # (name, location)
        self.seen_unions = set()  # (name, location)
        self.enum_members = {}  # name -> (library, list of (member_name, value) tuples, underlying_type)

        # Store captured macros by library: library -> {macro_name: value}
        self.captured_macros = {}  # library -> {macro_name: value}

    def _add_to_library_collection(self, collection: dict, library: str, item: str):
        """Add an item to a library-specific collection"""
        if library not in collection:
            collection[library] = []
        collection[library].append(item)

    def _clear_state(self):
        """Clear all accumulated state for a new generation run"""
        self.generated_functions.clear()
        self.generated_structs.clear()
        self.generated_unions.clear()
        self.generated_enums.clear()
        self.seen_functions.clear()
        self.seen_structs.clear()
        self.seen_unions.clear()
        self.enum_members.clear()
        self.captured_macros.clear()
        self.source_file = None

    def _extract_macros_from_file(self, file_path: str, patterns: list[str]) -> dict[str, str]:
        """Numeric-only extractor (legacy signature, retained for internal tests).

        Forwards to `_extract_typed_macros_from_file` treating every pattern as
        ``numeric``, and strips the kind from each entry so the return shape stays
        ``{name: value}``.
        """
        typed = [(p, "numeric") for p in patterns]
        result = self._extract_typed_macros_from_file(file_path, typed)
        return {name: value for name, (value, _kind) in result.items()}

    def _extract_typed_macros_from_file(
        self,
        file_path: str,
        typed_patterns: list[tuple[str, str]],
    ) -> dict[str, tuple[str, str]]:
        """Extract ``#define`` macros from a header, dispatching by pattern kind.

        ``typed_patterns`` is a list of ``(regex, kind)`` pairs where ``kind`` is either
        ``"string"`` or ``"numeric"``. Each macro is tested against the patterns for its
        kind:

        - ``"string"``: the macro body must be a single C string literal (``"..."``).
          No expansion is done — string macros that reference other identifiers are
          out of scope. The stored value is the literal including the bounding quotes.
        - ``"numeric"``: the body is expanded against the file's full macro table,
          C casts are stripped, and the result must pass `_is_numeric_macro_value`.

        Returns a dict ``{name: (value, kind)}`` so callers can route emit decisions
        (enum vs. UTF-8 property) without re-classifying.
        """
        macros: dict[str, tuple[str, str]] = {}
        table = self._scan_macros(file_path)

        numeric_patterns = [p for p, k in typed_patterns if k != "string"]
        string_patterns = [p for p, k in typed_patterns if k == "string"]

        for name, (params, body) in table.items():
            if params is not None:
                continue  # function-like macros stay in the table only as expansion targets

            wants_numeric = any(re.fullmatch(p, name) for p in numeric_patterns)
            wants_string = any(re.fullmatch(p, name) for p in string_patterns)

            # Prefer the string check first when the macro body literally looks like a
            # quoted string — that way `<constants type="string">` doesn't accidentally
            # lose to a wider `numeric` pattern that happens to also match the name.
            if wants_string and self._is_string_macro_value(body):
                macros[name] = (body, "string")
                continue

            if wants_numeric:
                value = self._expand_macros(body, table)
                value = self._strip_c_casts(value)

                # Legacy single-arg cast-macro form `WRAP(value)` (e.g. SDL_UINT64_C(0x123)).
                # Run AFTER expansion so we only fall back when expansion didn't replace
                # the wrapper.
                cast_match = re.match(r'^\w+\((.*)\)$', value)
                if cast_match:
                    value = cast_match.group(1).strip()

                if self._is_numeric_macro_value(value):
                    macros[name] = (value, "numeric")

        return macros

    @staticmethod
    def _is_string_macro_value(value: str) -> bool:
        """True if `value` is a single C string literal (e.g. `"hello"`).

        Backslash escapes are honored so that `"a\"b"` is recognized as one literal,
        not a quote-balanced pair. Concatenated literals like `"a" "b"` are rejected;
        we don't try to fuse them.
        """
        if len(value) < 2 or value[0] != '"' or value[-1] != '"':
            return False
        i = 1
        end = len(value) - 1
        while i < end:
            if value[i] == '\\' and i + 1 < end:
                i += 2
            elif value[i] == '"':
                return False
            else:
                i += 1
        return True

    def _scan_macros(self, file_path: str) -> dict[str, tuple[list[str] | None, str]]:
        """Pass-1 scan: turn every `#define` in a file into a lookup table.

        Returns a dict from macro name to `(params, body)` where:
          - object-like macros (`#define NAME body`) have `params=None`
          - function-like macros (`#define NAME(arg1, arg2) body`) have `params=[...]`

        Bodies are stripped of trailing `/* ... */` comments and trailing commas to
        match the legacy single-pass behavior. Multi-line continuations (backslash-
        newline) are not handled — same limitation the previous scanner had.
        """
        # Function-like has to be tried first because its `NAME(` opening would otherwise
        # be consumed by the object-like `\w+` group and leave `(args) body` as the value.
        func_re = re.compile(r'^\s*#\s*define\s+(\w+)\(([^)]*)\)\s+(.+?)(?://.*)?$')
        obj_re = re.compile(r'^\s*#\s*define\s+(\w+)\s+(.+?)(?://.*)?$')
        table: dict[str, tuple[list[str] | None, str]] = {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    fm = func_re.match(line)
                    if fm:
                        name = fm.group(1)
                        params = [p.strip() for p in fm.group(2).split(',') if p.strip()]
                        body = self._clean_macro_body(fm.group(3))
                        table[name] = (params, body)
                        continue
                    om = obj_re.match(line)
                    if om:
                        name = om.group(1)
                        body = self._clean_macro_body(om.group(2))
                        table[name] = (None, body)
        except Exception:
            pass

        return table

    @staticmethod
    def _clean_macro_body(body: str) -> str:
        body = body.strip()
        body = re.sub(r'/\*.*?\*/', '', body).strip()
        return body.rstrip(',')

    def _expand_macros(self, value: str, macros: dict, max_depth: int = 8) -> str:
        """Iteratively substitute identifier and function-call references in `value`
        until the value stops changing or we hit `max_depth`.

        The depth cap is a hard stop against self-referential macros (`#define FOO FOO`)
        and mutually-referential pairs; we'd rather return a partially-expanded value the
        numeric check rejects than hang.
        """
        for _ in range(max_depth):
            new_value = self._expand_once(value, macros)
            if new_value == value:
                return value
            value = new_value
        return value

    def _expand_once(self, value: str, macros: dict) -> str:
        """One substitution pass over `value`.

        Walks the string left-to-right. When we hit an identifier, decide:
        - if it's followed by `(`, treat it as a function-like macro call and substitute
          the body with the args bound to the parameter names;
        - otherwise treat it as an object-like macro reference and substitute its body.

        Identifiers inside `"..."` string literals are skipped so that string-valued
        macros aren't corrupted by accidental substitution.
        """
        ident_re = re.compile(r'[A-Za-z_]\w*')
        out: list[str] = []
        i = 0
        n = len(value)

        while i < n:
            ch = value[i]

            if ch == '"':
                # Copy a string literal verbatim, honoring backslash escapes so that an
                # escaped `\"` doesn't terminate the string prematurely.
                j = i + 1
                while j < n:
                    if value[j] == '\\' and j + 1 < n:
                        j += 2
                    elif value[j] == '"':
                        j += 1
                        break
                    else:
                        j += 1
                out.append(value[i:j])
                i = j
                continue

            if ch.isalpha() or ch == '_':
                m = ident_re.match(value, i)
                assert m is not None  # the leading-char check above guarantees this
                name = m.group(0)
                end = i + len(name)

                if end < n and value[end] == '(':
                    # Possible function-like call.
                    close = self._find_matching_paren(value, end)
                    if close is not None and name in macros and macros[name][0] is not None:
                        params, body = macros[name]
                        args = self._split_macro_args(value[end + 1:close])
                        if len(args) == len(params):
                            out.append(self._substitute_params(body, params, args))
                            i = close + 1
                            continue
                    # Not a known function-like macro (or arity mismatch): leave it alone.
                    out.append(name)
                    i = end
                    continue

                # Bare identifier.
                if name in macros and macros[name][0] is None:
                    out.append(macros[name][1])
                else:
                    out.append(name)
                i = end
            else:
                out.append(ch)
                i += 1

        return ''.join(out)

    @staticmethod
    def _find_matching_paren(s: str, open_idx: int) -> int | None:
        """Return the index of the `)` that closes the `(` at `open_idx`, or None
        if the parens never balance."""
        depth = 0
        for i in range(open_idx, len(s)):
            if s[i] == '(':
                depth += 1
            elif s[i] == ')':
                depth -= 1
                if depth == 0:
                    return i
        return None

    @staticmethod
    def _split_macro_args(args_str: str) -> list[str]:
        """Split a comma-separated function-like macro argument list, respecting paren
        depth so that `(a, b)` inside an argument is not split into two args."""
        if args_str.strip() == '':
            return []
        args: list[str] = []
        buf: list[str] = []
        depth = 0
        for ch in args_str:
            if ch == ',' and depth == 0:
                args.append(''.join(buf).strip())
                buf = []
            else:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                buf.append(ch)
        args.append(''.join(buf).strip())
        return args

    @staticmethod
    def _substitute_params(body: str, params: list[str], args: list[str]) -> str:
        """Replace every whole-word occurrence of each parameter name in `body` with the
        corresponding argument text. Identifiers inside string literals are not skipped
        here because function-like macro bodies that contain strings AND reference params
        in them are vanishingly rare in C and unsupported."""
        mapping = dict(zip(params, args))

        def repl(m: re.Match) -> str:
            name = m.group(0)
            return mapping[name] if name in mapping else name

        return re.sub(r'\b[A-Za-z_]\w*\b', repl, body)

    def _strip_c_casts(self, value: str) -> str:
        """Strip C-style casts `(IDENT)` from a macro value when they sit in front of a
        numeric token.

        The lookahead is what makes this safe: we only remove `(name)` when the next
        non-space character is a digit, opening paren, minus, or bitwise NOT — i.e. the
        start of a numeric expression that the cast is converting. Parens around a bare
        identifier (e.g. `(x)+1`) are left alone, and parens around a number (e.g. `(1)`)
        are not casts so the leading-letter requirement on the identifier skips them.
        """
        # Match a `(IDENT)` or `(IDENT IDENT ...)` cast where each token is whitespace-
        # separated. Covers `(uint32_t)`, `(unsigned int)`, `(long long)`, etc. We do not
        # try to handle pointer casts (`(int*)`) — those contain `*` and the numeric check
        # would reject the surrounding expression anyway.
        cast_pattern = re.compile(
            r'\(\s*[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*\s*\)\s*(?=[\d(\-~])'
        )
        # Loop until stable: nested casts like `((Foo)(Bar)0)` need a couple of passes.
        prev = None
        result = value
        while prev != result:
            prev = result
            result = cast_pattern.sub('', result)
        return result

    def _is_numeric_macro_value(self, value: str) -> bool:
        """Check if a macro value looks numeric (number, cast, or simple expression)

        Returns True for:
        - Plain numbers: 0x123, 123, -1
        - Cast expressions: SDL_UINT64_C(0x123)
        - Simple arithmetic: (1 << 5)

        Returns False for:
        - Identifier references: SDL_WINDOW_SOMETHING (would need evaluation)
        """
        # If it contains bare uppercase identifiers (not in function calls), skip it
        # This catches things like "SDL_WINDOW_HIGH_PIXEL_DENSITY" which reference other macros
        # Pattern: uppercase identifier that's not immediately followed by (
        if re.match(r'^[A-Z_][A-Z0-9_]+$', value):
            return False

        # Check if it's a plain number (hex, decimal, negative) with optional suffixes (u, l, ul, etc.)
        if re.match(r'^-?\d+[uUlL]*$', value) or re.match(r'^0x[0-9A-Fa-f]+[uUlL]*$', value):
            return True

        # Check if it's a cast/macro call with numeric content: NAME(0x...)
        if re.match(r'^\w+\(.*\)$', value):
            return True

        # Attempt to accept numeric expressions (including bitshifts) with suffixes such as 'u' or 'ul'.
        # Strategy: strip common unsigned/long suffixes that follow numeric tokens, then validate the
        # cleaned expression only contains numeric/hex tokens, operators and parentheses.
        try:
            # Remove suffix letters (u, U, l, L) that immediately follow a hex/decimal digit
            cleaned = re.sub(r'([0-9A-Fa-f])([uUlL]+)\b', r'\1', value)

            # Allowable characters after cleaning: digits, hex prefix x/X, whitespace, parentheses,
            # shift operators (<,>), bitwise operators (|,&,^,~), arithmetic (+-*/%), and hex digits.
            if re.match(r'^[\s0-9A-Fa-fxX()<>|&\^~+\-*/%]+$', cleaned):
                return True
        except re.error:
            # If regex operations fail for any reason, fall back to conservative False
            pass

        # Default to False for anything else
        return False

    def _is_system_header(self, file_path: str) -> bool:
        """Check if a file path is a system header that should be excluded"""
        path = Path(file_path).resolve()
        path_str = str(path)

        # Standard C library headers to exclude  - check filename first
        c_std_headers = {
            "assert.h",
            "complex.h",
            "ctype.h",
            "errno.h",
            "fenv.h",
            "float.h",
            "inttypes.h",
            "iso646.h",
            "limits.h",
            "locale.h",
            "math.h",
            "setjmp.h",
            "signal.h",
            "stdalign.h",
            "stdarg.h",
            "stdatomic.h",
            "stdbool.h",
            "stddef.h",
            "stdint.h",
            "stdio.h",
            "stdlib.h",
            "stdnoreturn.h",
            "string.h",
            "tgmath.h",
            "threads.h",
            "time.h",
            "uchar.h",
            "wchar.h",
            "wctype.h",
            "alloca.h",
        }

        filename = path.name
        if filename in c_std_headers:
            return True

        # System directories to exclude entirely
        system_paths = [
            "/usr/include/c++",
            "/usr/include/x86_64-linux-gnu",
            "/usr/include/aarch64-linux-gnu",
            "/usr/lib/gcc",
            "/usr/lib/clang",
            "/usr/local/include",
        ]

        if any(path_str.startswith(sys_path) for sys_path in system_paths):
            return True

        # Filter any header directly in /usr/include or in system subdirectories
        if path_str.startswith("/usr/include/"):
            relative = path_str[len("/usr/include/") :]

            # Filter all headers directly in /usr/include (no subdirectory)
            if "/" not in relative:
                return True

            # Also filter known system subdirectories
            first_part = relative.split("/")[0]
            system_subdirs = {
                "sys",
                "bits",
                "gnu",
                "asm",
                "asm-generic",
                "linux",
                "arpa",
                "net",
                "netinet",
                "rpc",
                "scsi",
                "protocols",
            }
            if first_part in system_subdirs:
                return True

        return False

    def process_cursor(self, cursor):
        """Recursively process AST nodes"""
        # Note: We don't filter files here anymore - we need to see all typedefs
        # to build a complete type resolution map. Filtering happens during code generation.

        if cursor.kind == CursorKind.FUNCTION_DECL:
            # Only generate code for non-system headers
            if cursor.location.file:
                file_path = str(cursor.location.file)
                if self._is_system_header(file_path):
                    # Don't generate code but still recurse
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
            # Check if this function should be removed
            if self.type_mapper.should_remove(cursor.spelling):
                # Skip this function entirely
                for child in cursor.get_children():
                    self.process_cursor(child)
                return
            # Check if we've already generated this function
            # Use global deduplication to avoid duplicate partial methods
            func_key = cursor.spelling  # Global deduplication by function name
            if func_key not in self.seen_functions:
                code = self.code_generator.generate_function(cursor, self.current_library)
                if code:
                    self._add_to_library_collection(self.generated_functions, self.current_library, code)
                    self.seen_functions.add(func_key)

        elif cursor.kind == CursorKind.STRUCT_DECL:
            if cursor.is_definition():
                # Skip anonymous structs - they are handled inline by their parent struct
                if cursor.spelling and "anonymous" in cursor.spelling.lower():
                    return
                # Only generate code for non-system headers
                if cursor.location.file:
                    file_path = str(Path(cursor.location.file.name).resolve())
                    if self._is_system_header(file_path):
                        # Don't generate code but still recurse
                        for child in cursor.get_children():
                            self.process_cursor(child)
                        return
                # Check if this struct should be removed
                if cursor.spelling and self.type_mapper.should_remove(cursor.spelling):
                    # Skip this struct entirely
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
                # Use global deduplication to avoid duplicate struct definitions
                struct_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                if struct_key not in self.seen_structs:
                    code = self.code_generator.generate_struct(cursor)
                    if code:
                        self._add_to_library_collection(self.generated_structs, self.current_library, code)
                        self.seen_structs.add(struct_key)
                        # Also mark as seen by name only to prevent opaque type generation
                        if cursor.spelling:
                            self.seen_structs.add((cursor.spelling, None, None))

        elif cursor.kind == CursorKind.UNION_DECL:
            if cursor.is_definition():
                # Skip anonymous unions - they are handled inline by their parent struct
                if cursor.spelling and "anonymous" in cursor.spelling.lower():
                    return
                # Only generate code for non-system headers
                if cursor.location.file:
                    file_path = str(Path(cursor.location.file.name).resolve())
                    if self._is_system_header(file_path):
                        # Don't generate code but still recurse
                        for child in cursor.get_children():
                            self.process_cursor(child)
                        return
                # Check if this union should be removed
                if cursor.spelling and self.type_mapper.should_remove(cursor.spelling):
                    # Skip this union entirely
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
                # Use global deduplication to avoid duplicate union definitions
                union_key = (cursor.spelling, str(cursor.location.file), cursor.location.line)
                if union_key not in self.seen_unions:
                    code = self.code_generator.generate_union(cursor)
                    if code:
                        self._add_to_library_collection(self.generated_unions, self.current_library, code)
                        self.seen_unions.add(union_key)

        elif cursor.kind == CursorKind.ENUM_DECL:
            if cursor.is_definition():
                # Only generate code for non-system headers
                if cursor.location.file:
                    file_path = str(Path(cursor.location.file.name).resolve())
                    if self._is_system_header(file_path):
                        # Don't generate code but still recurse
                        for child in cursor.get_children():
                            self.process_cursor(child)
                        return
                # Check if this enum should be removed
                if cursor.spelling and self.type_mapper.should_remove(cursor.spelling):
                    # Skip this enum entirely
                    for child in cursor.get_children():
                        self.process_cursor(child)
                    return
                # Collect enum members for merging (handle duplicate enum names)
                self._collect_enum_members(cursor)

        elif cursor.kind == CursorKind.TYPEDEF_DECL:
            # Build typedef resolution map for ALL typedefs (including system headers)
            type_name = cursor.spelling
            underlying_type = cursor.underlying_typedef_type
            if type_name and underlying_type:
                # Store the typedef mapping for later resolution
                self.type_mapper.register_typedef(type_name, underlying_type)

            # Only generate code for non-system opaque struct typedefs
            if cursor.location.file:
                file_path = str(cursor.location.file)
                if self._is_system_header(file_path):
                    return

            # Handle opaque struct typedefs (e.g., typedef struct SDL_Window SDL_Window;)
            # These are used as handles in C APIs
            children = list(cursor.get_children())
            if len(children) == 1:
                child = children[0]
                # Skip if already generated as a full struct for this library
                if (self.current_library, (type_name, None, None)) in self.seen_structs:
                    return

                # Check if it's a reference to a struct (TYPE_REF) or direct STRUCT_DECL
                if child.kind == CursorKind.TYPE_REF and child.spelling and "struct " in str(child.type.spelling):
                    # This is an opaque typedef like: typedef struct SDL_Window SDL_Window;
                    if type_name and type_name not in [
                        "size_t",
                        "ssize_t",
                        "ptrdiff_t",
                        "intptr_t",
                        "uintptr_t",
                        "wchar_t",
                    ]:
                        # Check if this type should be removed
                        if self.type_mapper.should_remove(type_name):
                            return

                        struct_key = (type_name, str(cursor.location.file), cursor.location.line)
                        # Use global deduplication
                        if struct_key not in self.seen_structs:
                            code = self.code_generator.generate_opaque_type(type_name)
                            if code:
                                self._add_to_library_collection(self.generated_structs, self.current_library, code)
                                self.seen_structs.add(struct_key)
                                self.seen_structs.add((type_name, None, None))
                                # Register as opaque type for pointer handling
                                self.type_mapper.opaque_types.add(type_name)
                                # Also generate an opaque type for the underlying struct name
                                # e.g. when typedef struct _XDisplay Display; we also want _XDisplay
                                try:
                                    underlying_spelling = str(child.type.spelling)
                                except Exception:
                                    underlying_spelling = None
                                if underlying_spelling:
                                    # strip 'struct ' prefix if present
                                    u_name = underlying_spelling
                                    for prefix in ["const ", "volatile ", "struct ", "union ", "class "]:
                                        if u_name.startswith(prefix):
                                            u_name = u_name[len(prefix) :]
                                            break
                                    if u_name and u_name != type_name:
                                        # Check if the underlying name should be removed
                                        if not self.type_mapper.should_remove(u_name):
                                            u_struct_key = (u_name, str(cursor.location.file), cursor.location.line)
                                            if u_struct_key not in self.seen_structs:
                                                u_code = self.code_generator.generate_opaque_type(u_name)
                                                if u_code:
                                                    self._add_to_library_collection(self.generated_structs, self.current_library, u_code)
                                                    self.seen_structs.add(u_struct_key)
                                                    self.seen_structs.add((u_name, None, None))
                                                    self.type_mapper.opaque_types.add(u_name)
                elif child.kind == CursorKind.STRUCT_DECL and not child.is_definition() and child.spelling:
                    # Check if this type should be removed
                    if self.type_mapper.should_remove(child.spelling):
                        return

                    # Direct forward declaration
                    struct_key = (child.spelling, str(cursor.location.file), cursor.location.line)
                    # Use global deduplication
                    if struct_key not in self.seen_structs:
                        code = self.code_generator.generate_opaque_type(child.spelling)
                        if code:
                            self._add_to_library_collection(self.generated_structs, self.current_library, code)
                            self.seen_structs.add(struct_key)
                            self.seen_structs.add((child.spelling, None, None))
                            # Register as opaque type for pointer handling
                            self.type_mapper.opaque_types.add(child.spelling)

        # Recurse into children
        for child in cursor.get_children():
            self.process_cursor(child)

    def prescan_opaque_types(self, cursor):
        """Pre-scan AST to identify opaque types before processing functions"""
        if cursor.kind == CursorKind.TYPEDEF_DECL:
            # Handle opaque struct typedefs (e.g., typedef struct SDL_Window SDL_Window;)
            children = list(cursor.get_children())
            if len(children) == 1:
                child = children[0]
                type_name = cursor.spelling

                # Check if it's a reference to a struct (TYPE_REF) or direct STRUCT_DECL
                if child.kind == CursorKind.TYPE_REF and child.spelling and "struct " in str(child.type.spelling):
                    # This is an opaque typedef like: typedef struct SDL_Window SDL_Window;
                    if type_name and type_name not in [
                        "size_t",
                        "ssize_t",
                        "ptrdiff_t",
                        "intptr_t",
                        "uintptr_t",
                        "wchar_t",
                    ]:
                        # Only register as opaque if not marked for removal
                        if not self.type_mapper.should_remove(type_name):
                            self.type_mapper.opaque_types.add(type_name)
                elif child.kind == CursorKind.STRUCT_DECL and not child.is_definition() and child.spelling:
                    # Direct forward declaration - only register if not marked for removal
                    if not self.type_mapper.should_remove(child.spelling):
                        self.type_mapper.opaque_types.add(child.spelling)

        # Recurse into children
        for child in cursor.get_children():
            self.prescan_opaque_types(child)

    def _collect_enum_members(self, cursor):
        """Collect enum members for merging duplicate enums"""
        from clang.cindex import CursorKind

        enum_name = cursor.spelling

        # Filter out invalid enum names (anonymous enums with full display name)
        if enum_name and ("unnamed" in enum_name or "(" in enum_name or "::" in enum_name):
            enum_name = None

        # For anonymous enums, derive name from common prefix
        if not enum_name:
            member_names = [
                child.spelling for child in cursor.get_children() if child.kind == CursorKind.ENUM_CONSTANT_DECL
            ]

            if member_names:
                # Find common prefix using the code generator's method
                common_prefix = self.code_generator._find_common_prefix(member_names)
                if common_prefix and len(common_prefix) > 2:
                    enum_name = common_prefix.rstrip("_")
                    if not enum_name:
                        # Will be assigned a unique name later
                        enum_name = None

        # Get underlying type for enum inheritance
        underlying_type = None
        if hasattr(cursor, "enum_type"):
            underlying_type = self.code_generator._map_enum_underlying_type(cursor.enum_type)

        # Collect members
        members = []
        for child in cursor.get_children():
            if child.kind == CursorKind.ENUM_CONSTANT_DECL:
                name = child.spelling
                value = child.enum_value
                members.append((name, value))

        if members:
            # Add to existing enum or create new entry
            if enum_name:
                if enum_name not in self.enum_members:
                    self.enum_members[enum_name] = (self.current_library, [], underlying_type)
                # Merge members, avoiding duplicates
                library, existing_members, existing_underlying_type = self.enum_members[enum_name]
                existing_member_names = {m[0] for m in existing_members}
                for member in members:
                    if member[0] not in existing_member_names:
                        existing_members.append(member)
                # Update underlying type if we have one and existing doesn't
                if underlying_type and not existing_underlying_type:
                    self.enum_members[enum_name] = (library, existing_members, underlying_type)
            else:
                # Anonymous enum - assign unique name
                anonymous_counter = 1
                while f"AnonymousEnum{anonymous_counter}" in self.enum_members:
                    anonymous_counter += 1
                enum_name = f"AnonymousEnum{anonymous_counter}"
                self.enum_members[enum_name] = (self.current_library, members, underlying_type)

    def generate(
        self,
        header_library_pairs: list[tuple[str, str]],
        output: str,
        include_dirs: Optional[list[str]] = None,
        ignore_missing: bool = False,
        skip_variadic: bool = False,
        library_class_names: Optional[dict[str, str]] = None,
        library_namespaces: Optional[dict[str, str]] = None,
        library_using_statements: Optional[dict[str, list[str]]] = None,
        visibility: str = "public",
        global_constants: Optional[list[tuple[str, str, str, bool]]] = None,
        global_defines: Optional[list[tuple[str, Optional[str]]]] = None,
        utf8_byte_overloads: bool = False,
        typed_fields: Optional[dict[tuple[str, str], str]] = None,
        typed_params: Optional[dict[tuple[str, str], str]] = None,
    ) -> dict[str, str]:
        """Generate C# bindings from C header file(s)

        Args:
            header_library_pairs: List of (header_file, library_name) tuples
            output: Output directory for generated files (required)
            include_dirs: List of directories to search for included headers
            ignore_missing: Continue processing even if some header files are not found
            skip_variadic: Skip generating bindings for variadic functions (default: True)
            library_class_names: Dict mapping library names to custom class names (defaults to NativeMethods)
            library_namespaces: Dict mapping library names to custom namespaces
            library_using_statements: Dict mapping library names to lists of using statements
            visibility: Visibility modifier for generated code ("public" or "internal")
            global_constants: List of (name, pattern, type) tuples for macro extraction, applied to all libraries
            global_defines: List of (name, value) tuples for compiler defines, applied to all headers
        """
        # Store visibility setting
        self.visibility = visibility

        # Initialize code generator with visibility, skip_variadic, byte-overload flag,
        # and the per-(struct, field) / per-(function, param) typed overrides.
        self.code_generator = CodeGenerator(
            self.type_mapper,
            visibility,
            skip_variadic,
            utf8_byte_overloads,
            typed_fields or {},
            typed_params or {},
        )

        # Store library class names
        self.library_class_names = library_class_names or {}

        # Store library namespaces
        self.library_namespaces = library_namespaces or {}

        # Store library using statements
        self.library_using_statements = library_using_statements or {}

        # Store global constants
        self.global_constants = global_constants or []

        # Store global defines
        self.global_defines = global_defines or []

        # Clear previous state
        self._clear_state()

        if include_dirs is None:
            include_dirs = []

        # Build clang arguments
        clang_args = ["-x", "c"]
        for include_dir in include_dirs:
            clang_args.append(f"-I{include_dir}")

        # Add global compiler defines
        for name, value in self.global_defines:
            if value is None or value == "":
                clang_args.append(f"-D{name}")
            else:
                clang_args.append(f"-D{name}={value}")

        # Add system include paths so clang can find standard headers
        # These paths are typical locations for system headers
        import subprocess

        try:
            # Try to get system include paths from clang itself
            result = subprocess.run(["clang", "-E", "-v", "-"], input=b"", capture_output=True, text=False, timeout=2)
            stderr = result.stderr.decode("utf-8", errors="ignore")
            in_includes = False
            for line in stderr.split("\n"):
                if "#include <...> search starts here:" in line:
                    in_includes = True
                    continue
                if in_includes:
                    if line.startswith("End of search list"):
                        break
                    # Extract path from line like " /usr/include"
                    path = line.strip()
                    if path and path.startswith("/"):
                        clang_args.append(f"-I{path}")
        except Exception:
            # Fallback to common paths if clang query fails
            # Don't print errors - this is a best-effort attempt
            for path in ["/usr/lib/clang/21/include", "/usr/local/include", "/usr/include"]:
                clang_args.append(f"-I{path}")

        # Parse each header file
        index = clang.cindex.Index.create()

        # Parse options to get detailed preprocessing info (for include directives)
        parse_options = clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD

        successfully_processed = 0

        for header_file, library_name in header_library_pairs:
            if not Path(header_file).exists():
                if ignore_missing:
                    print(f"Warning: Header file not found: {header_file}", file=sys.stderr)
                    continue
                else:
                    print(f"Error: Header file not found: {header_file}", file=sys.stderr)
                    raise FileNotFoundError(f"Header file not found: {header_file}")

            self.source_file = header_file
            self.current_library = library_name
            print(f"Processing: {header_file} -> {library_name}")
            if include_dirs:
                print(f"Include directories: {', '.join(include_dirs)}")

            tu = index.parse(header_file, args=clang_args, options=parse_options)

            # Check for parse errors (warnings don't stop processing)
            has_fatal_errors = False
            error_messages = []
            for diag in tu.diagnostics:
                if diag.severity >= clang.cindex.Diagnostic.Error:
                    error_msg = f"Error in {header_file}: {diag.spelling}"
                    print(error_msg, file=sys.stderr)
                    error_messages.append(diag.spelling)
                if diag.severity >= clang.cindex.Diagnostic.Fatal:
                    has_fatal_errors = True

            if has_fatal_errors:
                print(f"Fatal errors in {header_file}, cannot continue", file=sys.stderr)
                if error_messages:
                    raise RuntimeError(
                        f"Fatal parsing errors in {header_file}. Errors: {'; '.join(error_messages)}. Check include directories and header file accessibility."
                    )
                else:
                    raise RuntimeError(
                        f"Fatal parsing errors in {header_file}. Check include directories and header file accessibility."
                    )

            # Extract macros if global constants are defined
            if self.global_constants:
                if library_name not in self.captured_macros:
                    self.captured_macros[library_name] = {}

                # Tag each pattern with its emission kind so the per-file scanner can
                # filter accordingly. Anything other than "string" routes to the numeric
                # path (existing behavior).
                typed_patterns: list[tuple[str, str]] = []
                for const_name, const_pattern, const_type, const_flags in self.global_constants:
                    kind = "string" if const_type == "string" else "numeric"
                    typed_patterns.append((const_pattern, kind))

                # Extract macros from all files in the translation unit (not just the main header)
                # This includes all #included files, which is where macros like SDL_WINDOW_* live
                def collect_files(cursor, files_set):
                    """Recursively collect all file paths from the AST"""
                    if cursor.location.file:
                        file_path = str(cursor.location.file)
                        if not self._is_system_header(file_path):
                            files_set.add(file_path)
                    for child in cursor.get_children():
                        collect_files(child, files_set)

                all_files = set()
                collect_files(tu.cursor, all_files)

                # Extract macros from all non-system files
                for file_path in all_files:
                    file_macros = self._extract_typed_macros_from_file(file_path, typed_patterns)
                    self.captured_macros[library_name].update(file_macros)

                if self.captured_macros[library_name]:
                    print(f"Captured {len(self.captured_macros[library_name])} macro(s) for {library_name}")

            # Pre-scan for opaque types before processing functions
            self.prescan_opaque_types(tu.cursor)

            # Process the AST
            self.process_cursor(tu.cursor)

            # Only count as successfully processed after parsing succeeds
            successfully_processed += 1

        # Check if any files were successfully processed
        if successfully_processed == 0 and not ignore_missing:
            header_files = [pair[0] for pair in header_library_pairs]
            raise RuntimeError(
                f"No header files could be processed successfully. Files attempted: {', '.join(header_files)}. This usually indicates missing include directories or inaccessible header files."
            )

        # Generate merged enums from collected members
        for original_enum_name, (library, members, underlying_type) in sorted(self.enum_members.items()):
            if members:
                # Apply rename to enum name
                enum_name = self.type_mapper.apply_rename(original_enum_name)

                # Add inheritance clause if underlying type is not default 'int'
                inheritance_clause = ""
                if underlying_type and underlying_type != "int":
                    inheritance_clause = f" : {underlying_type}"

                # Check if this enum should have [Flags] attribute
                flags_attribute = ""
                if self.type_mapper.is_flag_enum(enum_name):
                    flags_attribute = "[Flags]\n"

                values_str = "\n".join([f"    {name} = {value}," for name, value in members])
                code = f"""{flags_attribute}{self.visibility} enum {enum_name}{inheritance_clause}
{{
{values_str}
}}
"""
                self._add_to_library_collection(self.generated_enums, library, code)

        # Generate enums or UTF-8 string members from captured macros using global constants
        for library_name in self.captured_macros:
            for const_name, const_pattern, const_type, const_flags in self.global_constants:
                wants_string = const_type == "string"

                # Get all macros matching this pattern, filtering by kind so that
                # a numeric constants group can't accidentally pick up a string macro
                # (or vice-versa) when their name patterns overlap.
                matching_macros: dict[str, str] = {}
                for macro_name, (macro_value, kind) in self.captured_macros[library_name].items():
                    if not re.fullmatch(const_pattern, macro_name):
                        continue
                    if wants_string and kind != "string":
                        continue
                    if not wants_string and kind != "numeric":
                        continue
                    matching_macros[macro_name] = macro_value

                if not matching_macros:
                    continue

                if wants_string:
                    # Each macro lands as a ReadOnlySpan<byte> member directly on the
                    # library's static class. We use the fully-qualified type so we don't
                    # need to add `using System;` to every generated file.
                    for macro_name, raw_string in sorted(matching_macros.items()):
                        renamed_member = self.type_mapper.apply_rename(macro_name)
                        prop = (
                            f"    {self.visibility} static System.ReadOnlySpan<byte> "
                            f"{renamed_member} => {raw_string}u8;\n"
                        )
                        self._add_to_library_collection(
                            self.generated_functions, library_name, prop
                        )
                    continue

                # Numeric (enum) path — unchanged from before.
                # Apply rename rules to the enum name and member names
                enum_name = self.type_mapper.apply_rename(const_name)

                # Build enum members with renamed names
                members = []
                for macro_name, macro_value in sorted(matching_macros.items()):
                    renamed_member = self.type_mapper.apply_rename(macro_name)
                    members.append(
                        f"    {renamed_member} = unchecked(({const_type})({macro_value})),"
                    )

                members_str = "\n".join(members)

                # Generate enum with specified type and optional [Flags] attribute
                flags_attr = "[Flags]\n" if const_flags else ""
                type_clause = f" : {const_type}" if const_type != "int" else ""
                code = f"""{flags_attr}{self.visibility} enum {enum_name}{type_clause}
{{
{members_str}
}}
"""
                self._add_to_library_collection(self.generated_enums, library_name, code)

        return self._generate_multi_file_output(output)

    def _generate_multi_file_output(self, output: str) -> dict[str, str]:
        """Generate multiple files, one per library"""
        if not output:
            raise ValueError("Output directory must be specified")

        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        # Get all libraries
        all_libraries = set()
        all_libraries.update(self.generated_enums.keys())
        all_libraries.update(self.generated_structs.keys())
        all_libraries.update(self.generated_unions.keys())
        all_libraries.update(self.generated_functions.keys())

        file_contents = {}

        # Create bindings.cs file with assembly attribute and default namespace
        # Note: DisableRuntimeMarshalling is excluded if variadic functions are present
        bindings_content = OutputBuilder.build(
            namespace="Bindings",
            enums=[],
            structs=[],
            unions=[],
            functions=[],
            class_name=NATIVE_METHODS_CLASS,
            include_assembly_attribute=True,
            visibility=self.visibility,
            has_variadic_functions=self.code_generator.has_variadic_functions,
        )
        bindings_file = output_path / "bindings.cs"
        bindings_file.write_text(bindings_content)
        file_contents["bindings.cs"] = bindings_content
        print(f"Generated assembly bindings: {bindings_file}")

        for library in sorted(all_libraries):
            # Get items for this library
            enums = self.generated_enums.get(library, [])
            structs = self.generated_structs.get(library, [])
            unions = self.generated_unions.get(library, [])
            functions = self.generated_functions.get(library, [])

            # Skip empty libraries
            if not any([enums, structs, unions, functions]):
                continue

            # Generate output for this library (without assembly attribute)
            class_name = self.library_class_names.get(library, NATIVE_METHODS_CLASS)
            library_namespace = self.library_namespaces.get(library, DEFAULT_NAMESPACE)
            library_using = self.library_using_statements.get(library, [])
            output = OutputBuilder.build(
                namespace=library_namespace,
                enums=enums,
                structs=structs,
                unions=unions,
                functions=functions,
                class_name=class_name,
                include_assembly_attribute=False,
                using_statements=library_using,
                visibility=self.visibility,
            )

            # Write to library-specific file
            library_file = output_path / f"{library}.cs"
            library_file.write_text(output)
            file_contents[f"{library}.cs"] = output

            print(f"Generated bindings for {library}: {library_file}")

        return file_contents
