# CsBindingGenerator - AI Assistant Context

**PURPOSE**: Essential context for AI assistants. For change history, see `git log`.

## Project Overview

Generates C# P/Invoke bindings from C headers using libclang. Modern LibraryImport attributes, multi-file output, regex renames.

## Architecture

```
C Headers → libclang → Generator → TypeMapper → CodeGenerator → C# Output
```

- **Generator** (`generator.py`): Parses C headers, manages deduplication, filters system headers
- **TypeMapper** (`type_mapper.py`): Maps C→C# types, applies renames, context-aware (is_struct_field, is_return_type)
- **CodeGenerator** (`code_generators.py`): Generates C# code, handles anonymous unions/structs, applies attributes
- **Config** (`config.py`): Parses XML configuration
- **Main** (`main.py`): CLI entry point (minimal args - most config in XML)

## Critical Concepts

### Deduplication (Multi-File Mode - Always Enabled)

Global deduplication by name only:
- Functions: First library wins by `cursor.spelling`
- Structs/Unions: First library wins by `(name, file, line)`

**CRITICAL**: Library order in XML matters - foundation libraries first.

### Type Mapping Context Awareness

- **`is_struct_field=True`**: Maps C `bool` → C# `byte` (avoids CS8500 managed type errors)
- **`is_return_type=True`**: Affects pointer type mapping

### Anonymous Unions/Structs

- Detected by "anonymous" in `cursor.spelling`
- NOT generated as standalone types
- Members flattened into parent struct
- Use `cursor.type.get_offset(field_name)` for parent-relative offsets (returns bits ÷ 8 = bytes)

### Variadic Functions

- **Default**: `...` parameter omitted (works with calling conventions, may cause stack issues)
- **`--use-variadic` flag**: Uses DllImport + `__arglist` (non-AOT compatible)

### Rename Rules

Stored as list: `[(pattern, replacement, is_regex), ...]`
- Applied in order, first match wins
- User writes `$1`, `$2` (converted to `\1`, `\2` internally)
- Uses `re.fullmatch()` for precise matching
- Post-processing uses word boundaries

**Conflict resolution**: Place specific rules before general ones:
```xml
<rename from="SDL_strcasecmp" to="SDL_strcasecmp"/>  <!-- Keep -->
<rename from="SDL_(.*)" to="$1" regex="true"/>        <!-- Strip rest -->
```

### System Header Filtering

`_is_system_header()` filters:
- `/usr/include/` direct files (no subdirectory)
- `/usr/include/{sys,bits,etc}/` subdirectories
- C standard library headers (c_std_headers set)
- `/usr/include/c++` paths

## XML Configuration

```xml
<bindings visibility="internal">
    <include_directory path="/custom/path"/>
    <rename from="PREFIX_(.*)" to="$1" regex="true"/>
    <remove pattern="DEPRECATED_.*" regex="true"/>
    <constants name="Flags" pattern="FLAG_.*" type="uint" flags="true"/>
    
    <library name="libname" namespace="Namespace" class="ClassName">
        <using namespace="System.Runtime.CompilerServices"/>
        <include file="/path/to/header.h"/>
    </library>
</bindings>
```

**Key attributes**:
- `<bindings>`: `visibility="public|internal"`
- `<rename>`: `from`, `to`, `regex="true|false"`
- `<remove>`: `pattern`, `regex="true|false"`
- `<constants>`: `name`, `pattern`, `type`, `flags="true|false"`
- `<library>`: `name`, `namespace`, `class` (default: "NativeMethods")
- `<using>`: `namespace`
- `<include>`: `file`

**Note**: Don't specify `/usr/include` - clang auto-detects it.

## CLI Arguments (Limited by Design)

- `-C/--config`: XML config file (default: cs-bindings.xml)
- `-o/--output`: Output directory (default: current)
- `--ignore-missing`: Continue if headers missing
- `--use-variadic`: Generate variadic functions with __arglist
- `--clang-path`: Path to libclang

## Known Edge Cases

- **Duplicate symbols**: Ensure library order in XML (foundation first) for global deduplication
- **Bool in structs**: Type mapper automatically converts bool→byte when `is_struct_field=True` to avoid managed type errors
- **System header leakage**: `_is_system_header()` must filter direct `/usr/include/` files and subdirectories
- **Anonymous unions**: Must detect "anonymous" in `cursor.spelling` and flatten members with parent-relative offsets
- **Incomplete arrays**: Handle `TypeKind.INCOMPLETEARRAY` → `nuint` for char*, `T*` for others

## libclang Key Concepts

- `cursor.spelling`: Entity name
- `cursor.location.file`: Source file
- `cursor.is_definition()`: True if definition (not declaration)
- `cursor.type.get_offset(field)`: Offset in **bits** (÷ 8 for bytes)
- `TypeKind.INCOMPLETEARRAY`: Array parameters like `items[]`

## Testing

Run: `source enter_devenv.sh && ./run_tests.sh`
- pytest 9.0.2, Python 3.13.11
- Current: 179 tests
- Test with real C code using `temp_header_file` fixture
- Verify struct offsets in bytes

## Development Workflow

1. Source env: `source enter_devenv.sh`
2. Make changes
3. Run: `./run_tests.sh`
4. Test projects in `test_dotnet/`: SDL3Test, LibtcodTest, FreeTypeTest
5. Each has `regenerate_bindings.sh` + `dotnet build`

## User Interaction Rules

1. Never assume pre-existing bugs
2. Don't try random fixes - ask if uncertain
3. Read error messages carefully
4. Check actual implementation (e.g., argparse in main.py) before documenting
5. Update this file only for architectural insights, not change history

---

**For change history: `git log`**


