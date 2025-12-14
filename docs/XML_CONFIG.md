# XML Configuration

The C# Binding Generator uses XML configuration files to define how bindings should be generated. This is the recommended way to configure the generator for most use cases.

## Quick Start

Create a `cs-bindings.xml` file in your project directory:

```xml
<bindings visibility="public">
    <!-- Include directories where headers can be found -->
    <include_directory path="/usr/include/SDL3"/>

    <!-- Rename rules to transform C names to C# names -->
    <rename from="SDL_" to="" regex="false"/>

    <!-- Define a library and its headers -->
    <library name="SDL3" namespace="SDL" class="NativeMethods">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>
</bindings>
```

Then run:
```bash
cs_binding_generator  # Automatically finds cs-bindings.xml
```

## Configuration Elements

### Root Element: `<bindings>`

The root element that contains all configuration.

**Attributes:**
- `visibility` (optional): Sets visibility for all generated code (`public` or `internal`, default: `public`)

```xml
<bindings visibility="internal">
    <!-- Configuration goes here -->
</bindings>
```

### Include Directories: `<include_directory>`

Specifies directories where header files can be found. Similar to `-I` flags in C compilers.

**Attributes:**
- `path` (required): Absolute or relative path to the include directory

```xml
<include_directory path="/usr/include"/>
<include_directory path="/usr/local/include"/>
<include_directory path="./include"/>
```

**Scope:**
- Can be defined globally (applies to all libraries)
- Can be defined inside `<library>` (applies only to that library)

### Renaming: `<rename>`

Transform C names to C# names. Applied to functions, types, enums, and constants.

**Attributes:**
- `from` (required): The C name or pattern to match
- `to` (required): The C# name or replacement pattern
- `regex` (optional): Whether to use regex matching (default: `false`)

**Important:** Renames are always global and apply to all libraries defined in the configuration.

#### Simple Rename

```xml
<!-- Rename specific identifiers -->
<rename from="SDL_Window" to="Window"/>
<rename from="SDL_CreateWindow" to="CreateWindow"/>
```

#### Regex Rename

```xml
<!-- Remove SDL_ prefix from all identifiers -->
<rename from="SDL_(.*)" to="$1" regex="true"/>

<!-- Remove prefix and suffix -->
<rename from="prefix_(.*)_suffix" to="$1" regex="true"/>
```

**Execution Order:**
- Non-regex renames are applied first (in definition order)
- Regex renames are applied second (in definition order)
- Multiple renames can chain together

### Removal: `<remove>`

Remove specific functions, types, or patterns from generation.

**Attributes:**
- `pattern` (required): The name or pattern to remove
- `regex` (optional): Whether to use regex matching (default: `false`)

**Important:** Removals are always global and apply to all libraries defined in the configuration.

```xml
<!-- Remove specific functions -->
<remove pattern="SDL_malloc"/>
<remove pattern="SDL_free"/>

<!-- Remove all functions matching a pattern -->
<remove pattern="SDL_.*_internal" regex="true"/>

<!-- Remove by prefix -->
<remove pattern="_private_.*" regex="true"/>
```

**Use Cases:**
- Exclude internal/private functions
- Remove memory management functions you'll handle differently
- Filter out platform-specific code
- Exclude deprecated APIs

### Constants: `<constants>`

Extract C macro constants as C# enums.

**Attributes:**
- `name` (required): Name of the C# enum to generate
- `pattern` (required): Pattern to match macro names
- `type` (optional): C# enum base type (default: `uint`)
- `flags` (optional): Add `[Flags]` attribute (default: `false`)

**Important:** Constants are always global and macros are extracted from all headers. The generated enums are placed in the library file that matches the most extracted macros.

```xml
<!-- Generate enum from SDL window flags -->
<constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>

<!-- Generate enum from init flags (no [Flags] attribute) -->
<constants name="InitFlags" pattern="SDL_INIT_.*"/>

<!-- Generate enum with specific type -->
<constants name="EventType" pattern="SDL_EVENT_.*" type="int"/>
```

**How it works:**
1. Generator scans header files for `#define` macros
2. Macros matching the pattern are collected
3. Only numeric values are included (hex, octal, or decimal)
4. A C# enum is generated with those values
5. Rename rules are applied to enum members

**Example:**

Input C header:
```c
#define SDL_WINDOW_FULLSCREEN    0x00000001
#define SDL_WINDOW_OPENGL        0x00000002
#define SDL_WINDOW_HIDDEN        0x00000004
#define SDL_WINDOW_BORDERLESS    0x00000008
```

Configuration:
```xml
<constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>
<rename from="SDL_WINDOW_(.*)" to="$1" regex="true"/>
```

Generated C#:
```csharp
[Flags]
public enum WindowFlags : ulong
{
    FULLSCREEN = unchecked((ulong)(0x00000001)),
    OPENGL = unchecked((ulong)(0x00000002)),
    HIDDEN = unchecked((ulong)(0x00000004)),
    BORDERLESS = unchecked((ulong)(0x00000008)),
}
```

### Libraries: `<library>`

Defines a native library and its headers.

**Attributes:**
- `name` (required): Native library name (used in `LibraryImport` attributes)
- `namespace` (optional): C# namespace for this library's bindings
- `class` (optional): Name of the static class containing P/Invoke methods (default: `NativeMethods`)

```xml
<library name="SDL3" namespace="SDL" class="SDL">
    <include file="/usr/include/SDL3/SDL.h"/>
</library>

<library name="libtcod" namespace="Libtcod" class="Tcod">
    <include file="/usr/include/libtcod/libtcod.h"/>
</library>
```

### Library Includes: `<include>`

Specifies which header files to process for a library.

**Attributes:**
- `file` (required): Path to the header file

```xml
<library name="mylib">
    <include file="/usr/include/mylib/core.h"/>
    <include file="/usr/include/mylib/extra.h"/>
</library>
```

### Library Using Statements: `<using>`

Add using statements to a library's generated file. Useful when one library references types from another.

**Attributes:**
- `namespace` (required): Namespace to add a using statement for

```xml
<library name="libtcod" namespace="Libtcod">
    <!-- libtcod uses SDL3 types, so add using statement -->
    <using namespace="SDL3"/>
    <include file="/usr/include/libtcod/libtcod.h"/>
</library>
```

## Complete Example

Here's a comprehensive example showing all features:

```xml
<bindings visibility="internal">
    <!-- Global include directories -->
    <include_directory path="/usr/include/libtcod"/>
    <include_directory path="/usr/include/SDL3"/>

    <!-- Specific renames (applied first) -->
    <rename from="SDL_aligned_alloc" to="AlignedAlloc"/>
    <rename from="SDL_aligned_free" to="AlignedFree"/>

    <!-- Regex renames (applied after specific renames) -->
    <rename from="SDL_(.*)" to="$1" regex="true"/>
    <rename from="TCOD_(.*)" to="$1" regex="true"/>

    <!-- Remove unwanted functions -->
    <remove pattern="SDL_malloc"/>
    <remove pattern="SDL_calloc"/>
    <remove pattern="SDL_realloc"/>
    <remove pattern="SDL_free"/>

    <!-- Extract constants as enums -->
    <constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>
    <constants name="InitFlags" pattern="SDL_INIT_.*" type="uint"/>

    <!-- SDL3 library -->
    <library name="SDL3" namespace="SDL3" class="SDL">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>

    <!-- LibTCOD library (uses SDL3 types) -->
    <library name="libtcod" namespace="Libtcod" class="Tcod">
        <using namespace="SDL3"/>
        <include file="/usr/include/libtcod/libtcod.h"/>
    </library>
</bindings>
```

## Usage

### Default Configuration File

By default, the generator looks for `cs-bindings.xml` in the current directory:

```bash
cs_binding_generator
```

This is equivalent to:
```bash
cs_binding_generator --config cs-bindings.xml
```

### Custom Configuration File

Specify a different configuration file:

```bash
cs_binding_generator --config my-bindings.xml
```

### Output Directory

Specify where to generate bindings:

```bash
cs_binding_generator --config cs-bindings.xml --output ./Generated
```

By default, output is placed in the current directory.

### Multi-File Output

The generator automatically creates separate files for each library defined in the XML config:

```
output/
├── bindings.cs          # Assembly attributes
├── SDL3.cs              # SDL3 library bindings
└── libtcod.cs          # libtcod library bindings
```

Each library file contains:
- Enums specific to that library
- Structs/unions for that library
- Functions with correct `LibraryImport` attributes
- Using statements as configured

## Advanced Features

### Complex Regex Patterns

Use advanced regex for sophisticated renaming:

```xml
<!-- Convert snake_case to PascalCase -->
<rename from="([a-z])_([a-z])" to="$1$2" regex="true"/>

<!-- Remove multiple prefixes -->
<rename from="(SDL|TCOD)_(.*)" to="$2" regex="true"/>

<!-- Preserve specific patterns -->
<rename from="SDL_SCANCODE_(.*)" to="Scancode$1" regex="true"/>
```

### Layered Removals

Combine simple and regex removals:

```xml
<!-- Remove specific functions -->
<remove pattern="internal_function"/>
<remove pattern="debug_print"/>

<!-- Remove all internal APIs -->
<remove pattern=".*_internal" regex="true"/>

<!-- Remove platform-specific code -->
<remove pattern=".*_win32" regex="true"/>
<remove pattern=".*_linux" regex="true"/>
```

### Multiple Constants Groups

Define multiple enum groups:

```xml
<constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>
<constants name="InitFlags" pattern="SDL_INIT_.*" type="uint"/>
<constants name="EventType" pattern="SDL_EVENT_.*" type="uint"/>
<constants name="KeyMod" pattern="SDL_KMOD_.*" type="ushort" flags="true"/>
```

## Tips and Best Practices

### 1. Start Simple

Begin with a minimal configuration and add features as needed:

```xml
<bindings>
    <library name="mylib">
        <include file="/usr/include/mylib.h"/>
    </library>
</bindings>
```

### 2. Use Visibility Carefully

Use `internal` visibility when generating bindings for a library wrapper:

```xml
<bindings visibility="internal">
    <!-- Your wrapper classes will be public, bindings will be internal -->
</bindings>
```

### 3. Order Renames Carefully

Specific renames before regex renames:

```xml
<!-- Specific exceptions first -->
<rename from="SDL_INIT_GAMECONTROLLER" to="InitGamepad"/>

<!-- General rule last -->
<rename from="SDL_INIT_(.*)" to="Init$1" regex="true"/>
```

### 4. Test Rename Rules

Generate with a simple case first to verify renames work as expected before applying to large headers.

### 5. Document Your Config

Add comments to explain non-obvious renames or removals:

```xml
<!-- Remove these because we provide safe wrappers -->
<remove pattern="SDL_malloc"/>
<remove pattern="SDL_free"/>

<!-- Rename to match C# naming conventions -->
<rename from="SDL_(.*)" to="$1" regex="true"/>
```

### 6. Use Constants for Flag Enums

Prefer extracting flag constants as enums with `[Flags]`:

```xml
<!-- Better type safety in C# -->
<constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>
```

### 7. Namespace Organization

Use namespaces to organize large libraries:

```xml
<library name="SDL3" namespace="MyApp.Graphics.SDL">
    <include file="/usr/include/SDL3/SDL.h"/>
</library>

<library name="libtcod" namespace="MyApp.Roguelike">
    <using namespace="MyApp.Graphics.SDL"/>
    <include file="/usr/include/libtcod/libtcod.h"/>
</library>
```

## Validation

The generator validates your XML configuration and reports errors:

```xml
<!-- ERROR: Missing required attribute -->
<library>
    <include file="test.h"/>
</library>
```

Error message:
```
ValueError: Library element missing 'name' attribute
```

Common validation errors:
- Missing required attributes
- Invalid visibility values
- Missing pattern in rename/remove
- Invalid XML syntax

## Programmatic Usage

You can also use the configuration parser programmatically:

```python
from cs_binding_generator.config import parse_config_file

# Parse the configuration
(
    header_library_pairs,
    include_dirs,
    renames,
    removals,
    library_class_names,
    library_namespaces,
    library_using_statements,
    visibility,
    global_constants,
) = parse_config_file("cs-bindings.xml")

# Use with generator
from cs_binding_generator.generator import CSharpBindingsGenerator

generator = CSharpBindingsGenerator()
result = generator.generate(
    header_library_pairs=header_library_pairs,
    include_dirs=include_dirs,
    # ... other parameters
)
```

## Migration from Command-Line

If you're currently using command-line arguments, here's how to migrate:

**Before (command-line):**
```bash
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -I /usr/include \
  -o ./bindings \
  -n SDL
```

**After (XML config):**
```xml
<bindings>
    <include_directory path="/usr/include"/>

    <library name="SDL3" namespace="SDL">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>
</bindings>
```

```bash
cs_binding_generator --config cs-bindings.xml --output ./bindings
```

## See Also

- [Architecture](ARCHITECTURE.md) - How the generator processes configuration
- [Troubleshooting](TROUBLESHOOTING.md) - Common configuration issues
- [Multi-File Output](MULTI_FILE_OUTPUT.md) - Understanding generated file structure
