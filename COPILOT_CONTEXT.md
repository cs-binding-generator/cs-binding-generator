# CsBindingGenerator - AI Assistant Context

**IMPORTANT**: Always update this file when you learn something new about the project architecture, patterns, or solutions to problems.

## Project Overview

CsBindingGenerator is a Python tool that generates C# P/Invoke bindings from C header files using libclang. It supports multi-file generation, type mapping, and rename rules including regex patterns.

## Core Architecture

### Pipeline Flow
```
C Headers → libclang → Generator → TypeMapper → CodeGenerator → C# Output
```

1. **Generator** (`cs_binding_generator/generator.py`): 
   - Orchestrates the entire process
   - Parses C headers via libclang (clang.cindex)
   - Manages deduplication strategies
   - Handles multi-file vs single-file modes
   - Processes cursors (AST nodes) recursively

2. **TypeMapper** (`cs_binding_generator/type_mapper.py`):
   - Maps C types to C# types (int → int, char* → string, etc.)
   - Applies rename rules (simple and regex)
   - Tracks opaque types for pointer handling
   - **Data structure**: `self.renames` is a LIST of tuples: `[(pattern, replacement, is_regex), ...]`

3. **CodeGenerator** (`cs_binding_generator/code_generators.py`):
   - Generates actual C# code for functions, structs, enums, unions
   - Handles attributes ([LibraryImport], [StructLayout], etc.)
   - Applies final post-processing renames

4. **Main/CLI** (`cs_binding_generator/main.py`):
   - Parses XML configuration files
   - Handles command-line arguments
   - Entry point: `generate()` function

## Critical Patterns & Rules

### Deduplication Strategies

**CRITICAL**: Multi-file mode has TWO different deduplication modes controlled by `self.multi_file` flag:

#### Multi-File Mode (`multi_file=True`)
- **Functions**: Global deduplication by function name only
  - Key format: `cursor.spelling` (just the function name)
  - Functions appear ONLY in the first library that processes them
  - **Order matters**: Process libraries in dependency order (foundation libraries first)
  
- **Structs**: Global deduplication
  - Key format: `(struct_name, file, line)`
  - Structs appear ONLY in the first library that processes them
  
- **Unions**: Global deduplication
  - Key format: `(union_name, file, line)`
  
- **Example**: If SDL3.h is processed before libtcod.h, SDL functions appear only in SDL3.cs, not in libtcod.cs (even though libtcod includes SDL headers)

#### Single-File Mode (`multi_file=False`)
- **Functions**: Library-specific deduplication
  - Key format: `(library_name, function_name)`
  - Same function can appear for different libraries in the single output file
  
- **Structs**: Library-specific deduplication
  - Key format: `(library_name, (struct_name, file, line))`
  
- **Unions**: Library-specific deduplication
  - Key format: `(library_name, (union_name, file, line))`

**Best Practice for Multi-File**: List libraries in XML config in dependency order - foundational libraries first, dependent libraries later. This ensures shared symbols are only generated once in the correct library.

### Rename Rules System

#### Simple Renames
```xml
<rename from="TCOD_Console" to="Console"/>
```

#### Regex Renames (Added Feature)
```xml
<rename from="SDL_(.*)" to="$1" regex="true"/>
<rename from="TCOD_(.+)_(.+)" to="$2$1" regex="true"/>
```

**Implementation Details**:
- Attribute: `regex="true"` in XML `<rename>` element
- Capture groups: Use `$1`, `$2` syntax (user-friendly)
- Internally converted to `\1`, `\2` for Python `re.sub()`
- Match semantics: Uses `re.fullmatch()` for precise identifier matching
- Order matters: Rules applied top-to-bottom (first match wins)
- Can mix simple and regex rules in same config

**Data Structure**:
```python
# OLD (before regex feature):
self.renames = {"from_name": "to_name"}

# NEW (after regex feature):
self.renames = [
    ("pattern", "replacement", False),  # Simple rename
    ("SDL_(.*)", "$1", True),           # Regex rename
]
```

**Key Methods**:
- `TypeMapper.add_rename(from_name, to_name, is_regex=False)`
- `TypeMapper.apply_rename(name)` - applies ordered rules
- `TypeMapper.get_all_renames()` - returns list of tuples
- `Generator.apply_final_renames(code)` - post-processing with regex

**Regex Capture Group Handling**:
In `Generator.apply_final_renames()`, capture group numbers are shifted by 1:
```python
# Pattern wrapped in outer group: r'\b(original_pattern)\b'
# So $1 becomes \2, $2 becomes \3, etc.
replacement = re.sub(r'\$(\d+)', lambda m: f'\\{int(m.group(1)) + 1}', replacement)
```

### Visibility System

**Feature**: Control access modifiers for all generated code (classes, structs, enums, unions, fields, functions).

**Configuration**:
```xml
<bindings visibility="internal">
    <!-- All generated code will use 'internal' access modifier -->
</bindings>
```

**Valid Values**:
- `"public"` (default) - All generated code is public
- `"internal"` - All generated code is internal
- Any other value prints an error and exits with code 1

**Scope**: Global setting that affects:
- Class declarations: `internal static unsafe partial class ClassName`
- Function declarations: `internal static partial void FunctionName()`
- Struct/Union declarations: `internal unsafe partial struct StructName`
- Struct/Union fields: `internal type fieldName;`
- Enum declarations: `internal enum EnumName`

**Implementation**:
- Parsed in `config.py` from `<bindings>` element
- Passed through `main.py` → `generator.py` → `code_generators.py`
- Applied during code generation to all declarations

**Use Case**: When generating bindings that should be internal to a library/assembly and not exposed to consumers.

### XML Configuration Format

```xml
<bindings visibility="internal">
    <!-- Global settings -->
    <include_directory path="/usr/include/SDL3"/>

    <!-- Rename rules (applied in order) -->
    <rename from="SDL_(.*)" to="$1" regex="true"/>
    <rename from="TCOD_Console" to="Console"/>

    <!-- Libraries -->
    <library name="SDL3">
        <namespace name="SDL3"/>
        <include file="/usr/include/SDL3/SDL.h"/>
        <include_directory path="/usr/include/SDL3"/>
    </library>
</bindings>
```

## File Locations & Purposes

- `cs_binding_generator/main.py` - CLI entry point, XML parsing
- `cs_binding_generator/generator.py` - Core generation logic, deduplication
- `cs_binding_generator/type_mapper.py` - Type mapping and rename rules
- `cs_binding_generator/code_generators.py` - C# code generation
- `tests/test_regex_renaming.py` - 7 tests for regex feature
- `tests/test_multi_file_deduplication.py` - Multi-file deduplication tests
- `docs/REGEX_RENAMING.md` - User documentation for regex feature

## Testing

- Framework: pytest 9.0.2
- Python version: 3.13.11
- Test count: 155 tests (all passing as of latest run)
- Run: `source enter_devenv.sh && python -m pytest`

### Important Test Files
- `test_xml_config.py` - XML configuration parsing including visibility feature
- `test_multi_file_deduplication.py` - Shared functions/structs between libraries
- `test_renaming.py` - Simple rename functionality
- `test_removal.py` - Removal functionality tests
- `test_generator.py` - Core generator tests
- `test_code_generators.py` - Code generation tests

## Common Issues & Solutions

### Issue: Duplicate Functions/Structs in Multi-File Mode
**Symptom**: Build errors like "Type 'NativeMethods' already defines a member called 'X'"
**Cause**: Shared headers (like SDL) included by multiple libraries, processed in wrong order
**Solution**: Order libraries in XML config correctly - foundation libraries first
**Example**: Put SDL3 library before libtcod library in `<bindings>` element
**How it works**: Global deduplication means first library to process a symbol "wins"
**Location**: XML config file library order

### Issue: Opaque Typedef Deduplication
**Symptom**: Structs appearing in both libraries when they shouldn't (or vice versa)
**Solution**: Ensure opaque typedef handling uses same deduplication strategy as regular structs
**Location**: `generator.py` lines ~230-260 in typedef handling

### Issue: Function Deduplication Mode Confusion
**Symptom**: Functions appearing or not appearing unexpectedly
**Solution**: Check `multi_file` flag - it changes deduplication behavior completely
**Multi-file=True**: Global deduplication (function appears once across all libraries)
**Multi-file=False**: Library-specific deduplication (function can appear for each library)
**Location**: `generator.py` lines ~112-130

### Issue: Test Files Must Be Updated When Changing Rename Structure
**Files to update**:
- `test_edge_cases.py`
- `test_multi_file_deduplication.py`
- `test_post_processing.py`
- `test_renaming.py`
**Pattern**: Change loops from `for from_name, to_name in renames.items()` to `for from_name, to_name, is_regex in renames`

### Issue: System Headers Leaking Into Generated Code
**Symptom**: Functions from system headers (like `strcasecmp`, `ffsll` from `strings.h`) appearing in generated bindings with wrong library name
**Root Cause**: System headers directly in `/usr/include/` were not being filtered out
**Problem**: `/usr/include/strings.h` is a POSIX header included transitively through `string.h` on Linux
**Solution**: Filter ANY header directly in `/usr/include/` (not just specific filenames or subdirectories)
**Location**: `generator.py` lines 89-99 in `_is_system_header()` method
**Fix Applied**: Check if file path is `/usr/include/<filename>` (no subdirectory) and filter it out
**Result**: System functions no longer appear in generated code, while actual library functions remain
**Testing**: Verified with SDL3.cs - system functions removed, SDL functions (like `SDL_strcasecmp`) still present

## Development Workflow

1. Make changes to Python source files
2. Run full test suite: `./run_tests.sh`
3. If tests fail, read error messages carefully (user emphasized: "don't assume")
4. For real-world testing, use test projects:
   - `test_dotnet/SDL3Test/` - SDL3 bindings
   - `test_dotnet/LibtcodTest/` - Libtcod + SDL3 bindings
   - `test_dotnet/FreeTypeTest/` - FreeType bindings

## Test Projects Structure

Each test project has:
- `cs-bindings.xml` - Configuration file
- `regenerate_bindings.sh` - Script to regenerate bindings
- `*.csproj` - .NET project file
- Build with: `dotnet build`

## Important Learnings

### User Interaction Patterns
1. **Never assume pre-existing bugs** - User will tell you if something was already broken
2. **Don't try random fixes** - Ask questions if uncertain
3. **Read error messages carefully** - They contain the actual problem
4. **Take smaller steps** - Better to make incremental changes than big rewrites

### Python/libclang Specifics
- Cursors represent AST nodes (CursorKind.FUNCTION_DECL, STRUCT_DECL, etc.)
- `cursor.spelling` = name of the entity
- `cursor.location.file` = source file path
- `cursor.is_definition()` = true if this is the definition (not just declaration)
- System headers should be filtered out via `_is_system_header()`

### Regex Pattern Best Practices
- Use `re.fullmatch()` not `re.match()` or `re.search()` for identifier matching
- Word boundaries in post-processing: `r'\b(pattern)\b'`
- Always test with both simple and complex patterns
- **Order matters**: More specific patterns should come BEFORE general ones
- First matching rule wins (rules processed top-to-bottom)

**Handling Rename Conflicts**:
When broad regex rules cause conflicts (e.g., stripping prefixes from multiple libraries):
1. Place specific "keep as-is" rules BEFORE general stripping rules
2. Example: To avoid conflicts from stripping SDL_ everywhere:
   ```xml
   <!-- Keep specific functions with prefix to avoid conflicts -->
   <rename from="SDL_strcasecmp" to="SDL_strcasecmp"/>
   <!-- Then strip SDL_ from everything else -->
   <rename from="SDL_(.*)" to="$1" regex="true"/>
   ```
3. The first rule prevents renaming, second rule strips the rest

## Recent Changes Log

### 2025-12-14: Visibility Attribute Feature - IMPLEMENTED AND WORKING
- **Status**: Feature fully implemented, all 155 tests passing
- Added global `visibility` attribute to `<bindings>` element in XML config
- Supports `"public"` (default) or `"internal"` values
- Invalid values print error message and exit with code 1
- Affects all generated code: classes, functions, structs, unions, enums, and fields

**Implementation Details**:
- `cs_binding_generator/config.py`: Parse visibility attribute, validate, and return
- `cs_binding_generator/main.py`: Pass visibility to generator
- `cs_binding_generator/generator.py`: Store visibility and pass to CodeGenerator and OutputBuilder
- `cs_binding_generator/code_generators.py`: Apply visibility to all generated declarations

**Testing**:
- Added 4 new unit tests in `test_xml_config.py`
- Updated all existing test files to handle new config return value
- Verified with LibtcodTest using `visibility="internal"`
- All generated code correctly uses internal access modifiers

**Use Case**:
- Internal bindings that should not be exposed to library consumers
- Encapsulation of P/Invoke declarations within assemblies

### 2025-12-13: Regex Rename Feature - IMPLEMENTED AND WORKING
- **Status**: Feature fully implemented, all 148 tests passing
- Changed renames from dict to list of (pattern, replacement, is_regex) tuples
- XML parsing updated to support `regex="true"` attribute
- TypeMapper.apply_rename() uses re.fullmatch() for precise matching
- Generator.apply_final_renames() handles capture group number shifting
- Opaque typedef deduplication fixed to respect multi_file flag
- Updated all test files to iterate over renames as list

**Implementation Details**:
- `cs_binding_generator/main.py`: Parse regex attribute, store as list of tuples
- `cs_binding_generator/type_mapper.py`: Apply renames with regex support, ordered rules
- `cs_binding_generator/generator.py`: Post-processing with regex, opaque typedef fixes
- Test files: Updated to unpack is_regex parameter

**Known Issue - Configuration, Not Code**:
- LibtcodTest with broad regex rules (strip all SDL_/TCOD_ prefixes) causes conflicts
- Functions from different libraries become identical after prefix stripping
- **Solution**: Add specific rename rules BEFORE general regex rules
- Example: Keep conflicting functions with prefixes, strip others
- Rule ordering: Specific rules first (checked top-to-bottom, first match wins)


### 2025-12-13: Fixed System Header Filtering - CRITICAL BUG FIX
- **Problem**: System functions (`strcasecmp`, `ffsll`, etc.) from `/usr/include/strings.h` appearing in generated SDL3.cs
- **Root Cause**: System headers directly in `/usr/include/` were only filtered by filename match or subdirectory match
- **Issue**: `strings.h` is a POSIX header (not in C standard), and sits directly in `/usr/include/` (not a subdirectory)
- **Why it leaked**: 
  - Not in `c_std_headers` set (only contains C standard library headers like `string.h`)
  - Not in a system subdirectory (like `sys/`, `bits/`, etc.)
  - Path-based filtering only checked specific system paths like `/usr/include/c++`
- **Solution**: Modified `_is_system_header()` to filter ANY header directly in `/usr/include/` (files with no subdirectory)
- **Location**: `generator.py` lines 89-99
- **Fix Details**: Added check for `if '/' not in relative:` to catch all direct `/usr/include/<filename>` headers
- **Testing**: All 141 tests passing; SDL3.cs no longer contains system functions; SDL functions remain intact
- **Impact**: Prevents system headers (POSIX, glibc, etc.) from polluting generated bindings regardless of transitive includes

### 2025-12-14: Documentation Cleanup - CLI Arguments Clarification
- **Status**: All documentation updated, 166 tests passing
- **Problem**: Documentation contained references to non-existent command-line arguments (`-i`, `-I`, `-n`, `--multi`)
- **Root Cause**: Tool evolved to be XML-configuration-only, but docs weren't fully updated

**CRITICAL FINDINGS**:

1. **Limited CLI Arguments - ONLY These Exist**:
   - `-C, --config CONFIG_FILE` - XML configuration file path (default: `cs-bindings.xml`)
   - `-o, --output DIRECTORY` - Output directory for generated files (default: current directory)
   - `--include-depth N` - Process included files up to depth N (overrides XML config if specified)
   - `--ignore-missing` - Continue processing even if some headers are not found
   - `--clang-path PATH` - Path to libclang library (if not in default location)
   - `-V, --version` - Show version number and exit

2. **XML Configuration Is PRIMARY and REQUIRED**:
   - ALL binding configuration must be in XML config file
   - This includes: input files, include directories, namespaces, libraries, renames, removals, constants
   - Command-line arguments are ONLY for runtime options (output path, include depth override)
   - See `main.py` lines 90-120 for argument parser definition

3. **System Include Paths Are Auto-Detected by Clang**:
   - Paths like `/usr/include` and `/usr/local/include` are automatically found
   - DO NOT need to be specified in XML config `<include_directory>` elements
   - Only specify non-standard paths (project headers, Homebrew, custom installs)

4. **Multi-File Output Is ALWAYS Enabled**:
   - No `--multi` flag exists
   - Multi-file output happens automatically when using XML config
   - Each library gets its own `.cs` file, plus a `bindings.cs` for assembly attributes
   - Cannot be disabled - this is the default behavior

**Files Updated**:
- `cs_binding_generator/main.py` - Fixed CLI help epilog examples
- `README.md` - Rewrote "Command Line Options" section completely
- `docs/INCLUDE_DIRECTORIES.md` - Complete rewrite for XML-only config
- `docs/XML_CONFIG.md` - Removed incorrect "Migration from Command-Line" section
- `docs/TROUBLESHOOTING.md` - Updated all sections to use XML configuration
- `docs/MULTI_FILE_OUTPUT.md` - Rewrote to remove `--multi` flag references
- `docs/INCLUDE_DEPTH.md` - NOT updated per user request (contains old CLI examples for reference)

**Testing Verification**:
```bash
source ./enter_devenv.sh
python -m pytest tests/ -v
# Result: 166 passed in 8.80s
```

**Key Takeaway for AI Assistants**:
- When asked about CLI usage, ALWAYS check `main.py` argparse configuration
- DO NOT suggest command-line arguments for binding configuration
- ALWAYS recommend using XML configuration file for binding settings
- The tool intentionally limits CLI to runtime options only

**User Quote**: "Check main.py you dingus" - always verify actual implementation before documenting

---

**Remember**: Always update this file when you learn something new about the project!
