# Architecture

This document explains how the C# Binding Generator works internally.

## Overview

The generator follows a multi-stage pipeline:

```
XML Config → Configuration Parsing → C Headers → libclang → AST → Macro Extraction → Type Mapping → Code Generation → Rename/Remove Rules → C# Output
```

## Components

### 1. Configuration Parser (`config.py`)

Parses XML configuration files to extract binding generation settings.

**Key function:**
- `parse_config_file()`: Parses cs-bindings.xml and returns configuration tuple

**Returns:**
- Header-library pairs: Which headers belong to which libraries
- Include directories: Where to find header files
- Renames: List of (from, to, is_regex) tuples for transforming names
- Removals: List of (pattern, is_regex) tuples for filtering
- Library class names: Custom static class names per library
- Library namespaces: Namespace for each library
- Library using statements: Cross-library dependencies
- Visibility: Global visibility setting (public/internal)
- Global constants: Macro patterns to extract as enums

**XML Elements Supported:**
- `<bindings>`: Root element with optional visibility attribute
- `<include_directory>`: Global and per-library include paths
- `<rename>`: Simple and regex-based name transformations
- `<remove>`: Filter out unwanted functions/types
- `<constants>`: Extract C macros as C# enums with optional [Flags]
- `<library>`: Define libraries with name, namespace, and class attributes
- `<include>`: Specify header files per library
- `<using>`: Add using statements for cross-library dependencies

**Validation:**
- Required attributes are checked
- Invalid visibility values cause errors
- Invalid XML syntax is reported

### 2. Main Entry Point (`main.py`)

Handles command-line interface and orchestrates the generation process.

**Key responsibilities:**
- Parse command-line arguments or load XML configuration
- Auto-discover cs-bindings.xml if no config specified
- Validate input parameters
- Invoke configuration parser if using XML config
- Invoke the generator with appropriate settings
- Handle output file writing (single or multi-file)

### 3. Generator (`generator.py`)

The main orchestrator that coordinates the entire generation process.

**Key classes:**
- `CSharpBindingsGenerator`: Main class that manages the generation pipeline

**Process flow:**
```python
1. Initialize libclang with include directories
2. Parse header files into AST (Abstract Syntax Tree)
3. Build file depth map based on include relationships
4. Pre-scan AST for opaque types
5. Extract macros from header files (for constants feature)
6. Process AST nodes (functions, structs, enums, typedefs)
7. Generate C# code using CodeGenerator (includes extracted constant enums)
8. Apply rename rules (simple first, then regex)
9. Apply removal rules to filter unwanted elements
10. Build final output using OutputBuilder (multi-file per library)
```

**Important methods:**
- `generate()`: Main entry point for generation
- `process_cursor()`: Recursively walks the AST
- `prescan_opaque_types()`: Identifies opaque struct typedefs
- `_build_file_depth_map()`: Tracks include hierarchy
- `_extract_macros_from_file()`: Scans header for #define macros
- `_is_numeric_macro_value()`: Validates macro values are numeric constants

### 4. Type Mapper (`type_mapper.py`)

Maps C types to appropriate C# types and applies name transformations.

**Key class:**
- `TypeMapper`: Handles all type conversions and name transformations

**Additional features:**
- `apply_rename()`: Applies rename rules to identifiers (simple then regex)
- `should_remove()`: Checks if an identifier matches removal patterns

**Mapping strategy:**
```python
# Basic types
int → int
float → float
bool → bool (with marshalling)

# Pointers
char* (param) → string
char* (return) → nuint (with helper method)
void* → nint
struct Foo* → Foo*  # Typed unsafe pointer
const struct Foo* → Foo*  # const stripped

# Special types
size_t → nuint
ssize_t → nint
```

**Key features:**
- Context-aware mapping (parameter vs return type)
- Opaque type tracking
- Multi-pass prefix stripping (const, struct, volatile)
- ELABORATED type handling

### 5. Code Generators (`code_generators.py`)

Generates C# code for different AST node types.

**Key classes:**
- `CodeGenerator`: Generates code for individual elements
- `OutputBuilder`: Assembles the final output file

**Generation methods:**
- `generate_function()`: Creates LibraryImport methods
- `generate_struct()`: Creates explicit layout structs
- `generate_union()`: Creates unions as explicit layout structs
- `generate_enum()`: Creates C# enums
- `generate_opaque_type()`: Creates empty struct handles
- `generate_constants_enum()`: Creates enums from extracted macros with optional [Flags] attribute

**Special handling:**
- Adds helper methods for char* returns
- Generates bool marshalling attributes
- Creates unsafe struct declarations
- Handles array fields with FieldOffset expansion

## Data Flow

### Phase 0: Configuration (Optional)
```
cs-bindings.xml
    ↓
parse_config_file()
    ↓
Configuration Tuple:
  - header_library_pairs
  - include_dirs
  - renames
  - removals
  - library_class_names
  - library_namespaces
  - library_using_statements
  - visibility
  - global_constants
```

### Phase 1: Parsing
```
C Header Files
    ↓
libclang.cindex.Index.parse()
    ↓
Translation Unit (AST)
```

### Phase 2: Analysis
```
AST Root Cursor
    ↓
prescan_opaque_types() → Identifies opaque types
    ↓
_build_file_depth_map() → Maps include hierarchy
    ↓
_extract_macros_from_file() → Collects #define constants (if constants configured)
```

### Phase 3: Processing
```
For each cursor in AST:
    ↓
Check if in allowed files (depth filter)
    ↓
Match cursor type:
    - FUNCTION_DECL → generate_function()
    - STRUCT_DECL → generate_struct()
    - UNION_DECL → generate_union()
    - ENUM_DECL → generate_enum()
    - TYPEDEF_DECL → check for opaque types
    ↓
Store generated code
```

### Phase 4: Post-Processing
```
Generated Code Elements
    ↓
Apply Rename Rules:
    - Simple renames first
    - Regex renames second
    ↓
Apply Removal Rules:
    - Filter out matched patterns
    ↓
Generate Constant Enums:
    - Create enums from extracted macros
    - Apply renames to enum members
    - Add [Flags] attribute if configured
```

### Phase 5: Output Generation
```
Processed Code Elements:
    - Enums (including constant enums)
    - Structs/Unions
    - Functions
    ↓
OutputBuilder.build() (per library)
    ↓
Multi-File Output:
    - bindings.cs (assembly attributes)
    - library1.cs (library 1 bindings)
    - library2.cs (library 2 bindings)

Each library file contains:
    - Using statements
    - Namespace
    - Enums
    - Structs
    - Class with LibraryImport methods
```

## Key Design Decisions

### Why Two-Pass Processing?

**Problem**: Functions may reference opaque types that appear later in the file.

**Solution**: Pre-scan for opaque types before processing functions.

```python
# Pass 1: Identify opaque types
prescan_opaque_types(ast)  # SDL_Window detected

# Pass 2: Process functions
process_cursor(ast)  # SDL_CreateWindow() knows SDL_Window is opaque
```

### Why Unsafe Pointers?

**Alternative**: Use `nint` for all pointers
**Choice**: Use typed pointers (`SDL_Window*`)

**Reasons:**
1. **Type safety**: Compiler catches type mismatches
2. **Better IDE support**: IntelliSense knows the type
3. **Clearer intent**: `SDL_Window*` vs `nint` is more readable
4. **Matches C API**: Closer to original C signatures

**Trade-off**: Requires `unsafe` keyword and compilation flag

### Why Explicit Layout?

**Alternative**: Use `[StructLayout(LayoutKind.Sequential)]`
**Choice**: Use `[StructLayout(LayoutKind.Explicit)]` with `[FieldOffset]`

**Reasons:**
1. **Precise control**: Matches C struct layout exactly
2. **Union support**: Can overlay fields at offset 0
3. **Padding awareness**: Explicit about field positions
4. **Cross-platform**: No reliance on C# packing rules

### Why Helper Methods for Strings?

C functions returning `char*`:
```c
const char* SDL_GetWindowTitle(SDL_Window* window);
```

Generated C#:
```csharp
// Raw pointer access
public static partial nuint SDL_GetWindowTitle(SDL_Window* window);

// Convenience wrapper
public static string? SDL_GetWindowTitleString(SDL_Window* window)
{
    var ptr = SDL_GetWindowTitle(window);
    return ptr == 0 ? null : Marshal.PtrToStringUTF8((nint)ptr);
}
```

**Reasons:**
1. **Flexibility**: Some scenarios need raw pointer
2. **Safety**: Wrapper handles null checks
3. **Convenience**: Most users want the string wrapper
4. **Performance**: Avoid marshalling overhead when not needed

## Extension Points

### Adding New Type Mappings

Edit `type_mapper.py`:

```python
# Add to CSHARP_TYPE_MAP in constants.py
CSHARP_TYPE_MAP = {
    TypeKind.LONG128: "Int128",  # New type
}

# Or handle in TypeMapper.map_type()
def map_type(self, ctype, is_return_type=False):
    # Custom logic for new types
    if ctype.kind == TypeKind.VECTOR:
        return "Vector128"
```

### Customizing Code Generation

Edit `code_generators.py`:

```python
def generate_function(self, cursor):
    # Add custom attributes
    code = f'[MyCustomAttribute]\n{code}'
    return code
```

### Filtering What Gets Generated

Edit `generator.py`:

```python
def process_cursor(self, cursor):
    # Skip certain patterns
    if cursor.spelling.startswith("_internal_"):
        return  # Don't generate
    
    # ... rest of processing
```

## Error Handling

### Parse Errors

Libclang diagnostics are checked:
```python
for diag in tu.diagnostics:
    if diag.severity >= clang.cindex.Diagnostic.Error:
        print(f"Error: {diag.spelling}")
```

### Type Mapping Failures

Unmappable types return `None`:
```python
if result_type is None:
    return ""  # Skip function
```

### Duplicate Prevention

Seen sets track generated items:
```python
self.seen_functions = set()  # (name, file, line)
self.seen_structs = set()
self.seen_enums = set()
```

## Performance Considerations

### Memory Usage

- AST is walked once per translation unit
- Generated code is accumulated in lists
- No intermediate file I/O during generation

### Speed Optimizations

- Pre-scan is a separate lightweight pass
- Depth filtering happens early in traversal
- Duplicate checks use set lookups (O(1))

### Scalability

Successfully tested with:
- SDL3: ~10,000 lines of output
- ~87 header files at depth 1
- Completes in seconds

## Testing Strategy

### Unit Tests

Test individual components in isolation:
- `test_type_mapper.py`: Type mapping logic
- `test_code_generators.py`: Code generation

### Integration Tests

Test end-to-end generation:
- `test_generator.py`: Full generation pipeline
- `test_cli.py`: Command-line interface

### Test Fixtures

Use temporary files and mock cursors:
```python
@pytest.fixture
def temp_header_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.h') as f:
        f.write("typedef struct Point { int x, y; } Point;")
        yield f.name
```

## Future Enhancements

Potential areas for improvement:

1. **Function pointer support**: Map to delegates
2. **Callback handling**: Generate C# delegate types
3. **Macro expansion**: Process simple #define values
4. **Bitfield support**: Handle bit-width fields
5. **Documentation comments**: Extract and preserve doxygen comments
6. **Source maps**: Track C header → C# line mapping
7. **Incremental generation**: Only regenerate changed definitions
8. **Custom type maps**: User-provided type override files
