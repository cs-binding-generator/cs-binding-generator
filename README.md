# C# Binding Generator

> **Note**: Most of the code in this repository was "vibe coded" with AI assistance, primarily using Claude Sonnet 4.5, GPT-4o, GPT-5 mini and Grok Code Fast 1.
> It is possible other models were also used in the mix. The author started this as an experiment to test how far AI has come in software
> development, but ended up creating an actually useful tool.

## What is this?

A Python-based tool that automatically generates C# P/Invoke bindings from C header files using libclang. It produces modern C# code using `LibraryImport` attributes and type-safe unsafe pointers for struct parameters.

The tool is configured primarily through XML configuration files, providing powerful features like renaming, filtering, and macro constant extraction.

## Features

- **XML Configuration**: Declare bindings configuration in a structured XML file
- **Modern C# Code Generation**: Uses `LibraryImport` (not deprecated `DllImport`)
- **Per-Library Binding**: Each header can specify its own library name for correct P/Invoke attributes
- **Type-Safe Pointers**: Generates typed pointers (`SDL_Window*`) instead of generic `nint`
- **Automatic Type Mapping**: Intelligently maps C types to C# equivalents
- **Renaming Support**: Simple and regex-based renaming rules to transform C names to C# conventions
- **Removal Support**: Filter out unwanted functions, types, or patterns
- **Macro Constants**: Extract C `#define` constants as C# enums with optional `[Flags]` attribute
- **String Handling**: Provides both raw pointer and helper string methods for `char*` returns
- **Struct Generation**: Creates explicit layout structs with proper field offsets
- **Union Support**: Converts C unions to C# structs with `LayoutKind.Explicit` and field offsets
- **Typedef Resolution**: Properly resolves struct-to-struct typedefs through the typedef chain
- **Multi-File Output**: Automatically splits bindings into separate files per library
- **Include Directory Support**: Specify additional header search paths
- **Opaque Type Support**: Handles opaque struct typedefs (like `SDL_Window`)
- **Visibility Control**: Generate public or internal bindings
- **Namespace Control**: Specify different namespaces per library
- **Custom Class Names**: Name the static class containing P/Invoke methods

## Documentation

- **[XML Configuration](docs/XML_CONFIG.md)** - Complete guide to XML configuration (recommended)
- **[Architecture](docs/ARCHITECTURE.md)** - Internal design and how the generator works
- **[Include Directories](docs/INCLUDE_DIRECTORIES.md)** - Managing header search paths
- **[Multi-File Output](docs/MULTI_FILE_OUTPUT.md)** - Understanding generated file structure
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd CsBindingGenerator

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package
pip install -e .
```

## Quick Start

### 1. Create Configuration File

Create `cs-bindings.xml` in your project directory:

```xml
<bindings visibility="public">
    <!-- Include directories where headers can be found -->
    <include_directory path="/usr/include/SDL3"/>

    <!-- Rename rules to transform C names to C# names -->
    <rename from="SDL_(.*)" to="$1" regex="true"/>

    <!-- Extract flag constants as enums -->
    <constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>

    <!-- Define the library -->
    <library name="SDL3" namespace="SDL" class="SDL">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>
</bindings>
```

### 2. Generate Bindings

```bash
cs_binding_generator  # Automatically finds cs-bindings.xml
```

Or specify a custom config file:

```bash
cs_binding_generator --config my-bindings.xml --output ./Generated
```

### 3. Use in Your Project

```csharp
using SDL;

// The generated bindings use modern LibraryImport
var window = SDL.CreateWindow("My Game", 800, 600, WindowFlags.WINDOW_SHOWN | WindowFlags.WINDOW_RESIZABLE);
```

## Configuration Examples

### Multiple Libraries

```xml
<bindings visibility="internal">
    <include_directory path="/usr/include/libtcod"/>
    <include_directory path="/usr/include/SDL3"/>

    <!-- Remove SDL_ and TCOD_ prefixes -->
    <rename from="SDL_(.*)" to="$1" regex="true"/>
    <rename from="TCOD_(.*)" to="$1" regex="true"/>

    <!-- Remove unwanted memory functions -->
    <remove pattern="SDL_malloc"/>
    <remove pattern="SDL_free"/>

    <!-- Extract constants -->
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

This generates:
- `bindings.cs` - Assembly attributes
- `SDL3.cs` - SDL3 bindings with renamed functions and extracted constants
- `libtcod.cs` - LibTCOD bindings with SDL3 using statement

### Advanced Renaming

```xml
<bindings>
    <!-- Specific renames (applied first) -->
    <rename from="SDL_aligned_alloc" to="AlignedAlloc"/>
    <rename from="SDL_aligned_free" to="AlignedFree"/>

    <!-- General pattern (applied after specific renames) -->
    <rename from="SDL_SCANCODE_(.*)" to="Scancode$1" regex="true"/>
    <rename from="SDL_(.*)" to="$1" regex="true"/>

    <library name="SDL3">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>
</bindings>
```

## Generated Output Example

When processing multiple libraries with XML configuration, each function gets the correct `LibraryImport` attribute:

**Input Configuration:**
```xml
<bindings>
    <rename from="SDL_(.*)" to="$1" regex="true"/>
    <rename from="TCOD_(.*)" to="$1" regex="true"/>

    <!-- Extract window flags as enum with [Flags] attribute -->
    <constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>

    <library name="SDL3" namespace="GameLibs" class="SDL">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>

    <library name="libtcod" namespace="GameLibs" class="Tcod">
        <include file="/usr/include/libtcod/libtcod.h"/>
    </library>
</bindings>
```

**Generated C# (SDL3.cs):**
```csharp
namespace GameLibs;

[Flags]
public enum WindowFlags : ulong
{
    FULLSCREEN = unchecked((ulong)(0x0000000000000001)),
    OPENGL = unchecked((ulong)(0x0000000000000002)),
    HIDDEN = unchecked((ulong)(0x0000000000000008)),
    // ...
}

public static unsafe partial class SDL
{
    [LibraryImport("SDL3", EntryPoint = "SDL_Init", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial int Init(uint flags);

    [LibraryImport("SDL3", EntryPoint = "SDL_CreateWindow", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial Window* CreateWindow(string title, int w, int h, ulong flags);
}
```

**Generated C# (libtcod.cs):**
```csharp
using SDL3;

namespace GameLibs;

public static unsafe partial class Tcod
{
    [LibraryImport("libtcod", EntryPoint = "TCOD_init", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial void init(int w, int h, string title);
}
```

## Command Line Options

The tool uses XML configuration files for all binding settings. Command-line arguments are limited to runtime options:

```bash
# Use default cs-bindings.xml in current directory
cs_binding_generator

# Specify custom config file
cs_binding_generator --config my-bindings.xml

# Specify output directory
cs_binding_generator --config bindings.xml --output ./Generated
```

### Available Command-Line Options

- `-C, --config CONFIG_FILE`: XML configuration file (default: `cs-bindings.xml` in current directory)
- `-o, --output DIRECTORY`: Output directory for generated files (default: current directory)
- `--ignore-missing`: Continue processing even if some header files are not found
- `--clang-path PATH`: Path to libclang library (if not in default location)
- `-V, --version`: Show version number and exit

**Note:** All binding configuration (input files, include directories, namespaces, renames, etc.) must be specified in the XML configuration file. See [XML Configuration](docs/XML_CONFIG.md) for details.

## How It Works

### Architecture

1. **Configuration Parsing**: Reads XML config file to get libraries, renames, removals, and constants
2. **Parsing**: Uses libclang to parse C header files into an AST (Abstract Syntax Tree)
3. **Type Discovery**: Pre-scans the AST to identify opaque types (empty struct typedefs)
4. **Macro Extraction**: Scans header files for `#define` macros matching constant patterns
5. **Code Generation**: Walks the AST and generates C# code for:
   - Enums → C# enums (including extracted macro constants)
   - Structs/Unions → C# structs with `[StructLayout(LayoutKind.Explicit)]`
   - Functions → C# static partial methods with `[LibraryImport]`
   - Opaque types → Empty C# structs for type-safe handles
6. **Post-Processing**: Applies rename and removal rules
7. **Multi-File Output**: Splits generated code into separate files per library

### Type Mapping

| C Type | C# Type | Notes |
|--------|---------|-------|
| `void` | `void` | |
| `int`, `long` | `int` | |
| `unsigned int` | `uint` | |
| `float`, `double` | `float`, `double` | |
| `char*` (param) | `string` | Auto-marshalled |
| `char*` (return) | `nuint` | Use helper method for string |
| `void*` | `nint` | Generic pointer |
| `struct Foo*` | `Foo*` | Typed unsafe pointer |
| `union Bar` | `Bar` | Struct with `LayoutKind.Explicit` |
| `const struct Foo*` | `Foo*` | Const stripped |
| `size_t` | `nuint` | |
| `bool` | `bool` | With marshalling attribute |

### Generated Code Example

Input C:
```c
#define SDL_WINDOW_FULLSCREEN 0x00000001
#define SDL_WINDOW_OPENGL     0x00000002

typedef struct SDL_Window SDL_Window;

SDL_Window* SDL_CreateWindow(const char* title, int x, int y, int w, int h, uint32_t flags);
void SDL_DestroyWindow(SDL_Window* window);
const char* SDL_GetWindowTitle(SDL_Window* window);
```

Configuration:
```xml
<bindings>
    <rename from="SDL_(.*)" to="$1" regex="true"/>
    <constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="uint" flags="true"/>

    <library name="SDL3" namespace="SDL">
        <include file="SDL.h"/>
    </library>
</bindings>
```

Output C#:
```csharp
namespace SDL;

[Flags]
public enum WindowFlags : uint
{
    FULLSCREEN = unchecked((uint)(0x00000001)),
    OPENGL = unchecked((uint)(0x00000002)),
}

public struct Window
{
}

public static unsafe partial class NativeMethods
{
    [LibraryImport("SDL3", EntryPoint = "SDL_CreateWindow", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial Window* CreateWindow(string title, int x, int y, int w, int h, uint flags);

    [LibraryImport("SDL3", EntryPoint = "SDL_DestroyWindow", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial void DestroyWindow(Window* window);

    [LibraryImport("SDL3", EntryPoint = "SDL_GetWindowTitle", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial nuint GetWindowTitle(Window* window);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static string? GetWindowTitleString(Window* window)
    {
        var ptr = GetWindowTitle(window);
        return ptr == 0 ? null : Marshal.PtrToStringUTF8((nint)ptr);
    }
}
```

## Testing

The project includes comprehensive tests using pytest:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=cs_binding_generator

# Run specific test
pytest tests/test_generator.py::TestCSharpBindingsGenerator::test_generate_with_flags_attribute -v
```

## Real-World Example: SDL3 + LibTCOD

This tool was developed and tested by generating bindings for SDL3 and LibTCOD. The generated files contain:
- Full API coverage for both libraries
- Type-safe window, renderer, and other opaque handle types
- Proper struct layouts with field offsets
- String marshalling helpers
- Extracted flag enums from macros
- Clean, renamed C# names without prefixes

See `test_dotnet/LibtcodTest/cs-bindings.xml` for a complete working example.

## Requirements

- Python 3.11+
- libclang
- clang headers installed on your system

### Installing libclang

**Ubuntu/Debian**:
```bash
sudo apt install libclang-dev python3-clang
```

**macOS**:
```bash
brew install llvm
```

**Arch Linux**:
```bash
sudo pacman -S clang python-clang
```

## Project Structure

```
CsBindingGenerator/
├── cs_binding_generator/
│   ├── __init__.py
│   ├── main.py              # CLI entry point
│   ├── generator.py         # Main orchestration
│   ├── type_mapper.py       # C to C# type mapping
│   ├── code_generators.py   # C# code generation
│   ├── config.py            # XML configuration parser
│   └── constants.py         # Shared constants
├── tests/
│   ├── test_generator.py
│   ├── test_type_mapper.py
│   ├── test_code_generators.py
│   ├── test_xml_config.py
│   └── ...
├── docs/
│   ├── XML_CONFIG.md        # XML configuration guide
│   ├── ARCHITECTURE.md
│   ├── INCLUDE_DIRECTORIES.md
│   ├── MULTI_FILE_OUTPUT.md
│   └── TROUBLESHOOTING.md
└── README.md
```

## Limitations

- Variadic functions are not supported (skipped)
- Complex macros with expressions are not extracted
- Bitfields in structs are not supported
- Function pointers are mapped to `nint`
- Requires manual handling of callbacks

## Contributing

Since this was an AI-assisted project, contributions are welcome! The codebase is designed to be readable and maintainable despite its AI origins.

## License

See LICENSE file for details.

## Acknowledgments

- Built with the power of AI (Claude Sonnet 4.5 and Grok Code Fast 1)
- Uses libclang for C parsing
- Inspired by the need for better SDL3 C# bindings
