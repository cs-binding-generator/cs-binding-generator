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

### Preprocessor Defines: `<define>`

Pass `-D` preprocessor flags to libclang when it parses each header. Use this to
flip feature flags, set platform sentinels, or expose configuration values that
the headers gate behind `#ifdef`.

**Attributes:**
- `name` (required): The macro name to define
- `value` (optional): The value to assign. Omit (or pass an empty string) to define
  the macro with no value, equivalent to a bare `-DNAME` flag

**Important:** Defines are always global and apply to every library/header that gets
parsed.

```xml
<!-- Bare define: -DENABLE_FEATURE -->
<define name="ENABLE_FEATURE"/>

<!-- Define with value: -DVERSION=123 -->
<define name="VERSION" value="123"/>

<!-- Useful for forcing a platform / SDK macro before include: -->
<define name="_GNU_SOURCE"/>
<define name="SDL_MAIN_HANDLED"/>
```

**Use cases:**
- Enable optional API blocks the headers gate behind `#ifdef`
- Force a platform identifier so cross-architecture headers pick the right branch
- Inject a build-flavor flag (debug/release/profile) into the parse

Note that defines affect what libclang *sees*, not what the generated C# code
does. They alter which functions, structs, and macros end up in the binding;
they don't insert anything into the C# output directly.

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

Extract C macro constants as either a C# enum (numeric values) or as UTF-8
`ReadOnlySpan<byte>` members on the library class (string values).

**Attributes:**
- `name` (required for numeric, optional for `type="string"`): Name of the C# enum
  to generate. String groups have no wrapper type, so the name is ignored.
- `pattern` (required): Pattern to match macro names
- `type` (optional, default `uint`): C# enum base type for numeric mode, or the
  literal value `string` to switch into UTF-8 string-constants mode
- `flags` (optional, default `false`): Add `[Flags]` attribute. Numeric mode only.

**Important:** Constants are always global and macros are extracted from all headers.
A constants group is emitted in every library whose translation unit captures at
least one matching macro. When two libraries share a header (transitive include),
the same enum will appear in both library files.

```xml
<!-- Numeric: flag enum from SDL window flags -->
<constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>

<!-- Numeric: plain enum (no [Flags]) -->
<constants name="InitFlags" pattern="SDL_INIT_.*"/>

<!-- Numeric: explicit base type -->
<constants name="EventType" pattern="SDL_EVENT_.*" type="int"/>

<!-- String: emits each match as a ReadOnlySpan<byte> on the library class -->
<constants pattern="SDL_PROP_.*_STRING" type="string"/>
```

**How numeric mode works:**
1. Scan every `#define` in each header into a per-file macro table, keeping both
   object-like (`#define NAME body`) and function-like (`#define NAME(arg) body`)
   forms.
2. For each pattern-matching object-like macro, expand its body against the table
   recursively (capped at 8 substitutions to bound self-referential cycles). This
   resolves chains like `#define A B` / `#define B 1` to `1`, and function-like
   calls like `SDL_BUTTON_MASK(SDL_BUTTON_LEFT)` to `(1u << ((1)-1))`.
3. Strip leading C-style casts such as `(SomeType)` when they sit in front of a
   numeric token, so `((SDL_AudioDeviceID) 0xFFFFFFFFu)` reduces to `(0xFFFFFFFFu)`.
4. Validate that the result is numeric (hex, decimal, bitwise/arithmetic expression).
   Macros that don't fully resolve are silently skipped.
5. Emit a C# enum with the surviving values; rename rules are applied to both the
   enum name and the member names.

**How string mode works:**
1. The same `#define` table is built, but candidate bodies are only accepted if
   they are a single quoted C string literal (e.g. `"hello"`). Identifier references
   inside string bodies are NOT expanded.
2. Each surviving macro is emitted as
   `public static System.ReadOnlySpan<byte> NAME => "literal"u8;` on the library's
   static class. No wrapper type is created, so `name=` on the `<constants>`
   element is unused in this mode.
3. Rename rules apply to the member name.

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

### UTF-8 Byte Overloads: `<utf8-byte-overloads/>`

Opt in to a second `[LibraryImport]` partial method for every non-variadic function
whose primary signature contains at least one `string?` parameter. The overload
swaps every `string?` for `byte*`, letting callers pass pre-encoded UTF-8 buffers
(u8 literals, pinned `ReadOnlySpan<byte>`, `byte[]` via `fixed`) to native code
without the `string` → marshaller → UTF-8 round trip.

**Attributes:** none. Presence of the element enables the feature.

```xml
<bindings>
    <utf8-byte-overloads/>
    <library name="SDL3" namespace="MyApp">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>
</bindings>
```

**Example:**

Input C:
```c
int SDL_SetStringProperty(unsigned int props, const char* name, const char* value);
```

Generated C# (both partials reference the same native symbol):
```csharp
[LibraryImport("SDL3", EntryPoint = "SDL_SetStringProperty", StringMarshalling = StringMarshalling.Utf8)]
[UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
public static partial int SDL_SetStringProperty(uint props, string? name, string? value);

[LibraryImport("SDL3", EntryPoint = "SDL_SetStringProperty", StringMarshalling = StringMarshalling.Utf8)]
[UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
public static partial int SDL_SetStringProperty(uint props, byte* name, byte* value);
```

Caller:
```csharp
fixed (byte* p = "SDL.gpu.shader.create.name"u8)
fixed (byte* v = nameBytes)
    SDL_SetStringProperty(props, p, v);
```

The C# compiler resolves overloads by argument type. The overload is only emitted
for non-variadic functions that have at least one `string?` param — functions with
no string params are left as-is. Non-string parameters (including bool with its
`[MarshalAs(UnmanagedType.I1)]` attribute) are forwarded verbatim into the overload.

### Flag Enums: `<flags>`

Mark **auto-discovered** C enums (those declared as `typedef enum { ... } Name;`
in the header) with the C# `[Flags]` attribute. Use this when the C author chose
a real `enum` over `#define` macros but the values are still bitmask flags.

This is distinct from `<constants flags="true">`:

- `<constants flags="true">` extracts `#define` macros into a NEW enum and tags
  that new enum with `[Flags]`.
- `<flags>` tags an EXISTING enum that the generator already discovered from
  a `typedef enum` in the source.

**Attributes:**
- `pattern` (required): The enum name to match (or a regex if `regex="true"`)
- `regex` (optional, default `false`): Treat `pattern` as a regular expression

**Important:** Flag patterns are global. The first matching pattern wins (no
chaining). Pattern matching uses `re.fullmatch`, so the pattern must match the
entire enum name.

```xml
<!-- Exact name match -->
<flags pattern="SDL_WindowFlags"/>

<!-- Regex: every enum whose name ends in `Flags` -->
<flags pattern=".*Flags" regex="true"/>

<!-- Combine specific overrides with a broad rule -->
<flags pattern="Permissions"/>
<flags pattern=".*Mode" regex="true"/>
```

**Example:**

Input C header:
```c
typedef enum {
    SDL_WINDOW_FULLSCREEN = 1,
    SDL_WINDOW_RESIZABLE = 2,
    SDL_WINDOW_HIDDEN    = 4
} SDL_WindowFlags;
```

Configuration:
```xml
<flags pattern="SDL_WindowFlags"/>
```

Generated C#:
```csharp
[Flags]
public enum SDL_WindowFlags
{
    SDL_WINDOW_FULLSCREEN = 1,
    SDL_WINDOW_RESIZABLE = 2,
    SDL_WINDOW_HIDDEN = 4,
}
```

Renames are applied after flag matching: if `<rename>` renames the enum, write
your `<flags>` pattern against the **renamed** name.

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

## See Also

- [Architecture](ARCHITECTURE.md) - How the generator processes configuration
- [Troubleshooting](TROUBLESHOOTING.md) - Common configuration issues
- [Multi-File Output](MULTI_FILE_OUTPUT.md) - Understanding generated file structure
