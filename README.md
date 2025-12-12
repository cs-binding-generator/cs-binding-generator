# C# Binding Generator

> **Note**: Most of the code in this repository was "vibe coded" with AI assistance, primarily using Claude Sonnet 4.5 and potentially other models. The author started this as an experiment to test how far AI has come in software development, but ended up creating an actually useful tool.

## What is this?

A Python-based tool that automatically generates C# P/Invoke bindings from C header files using libclang. It produces modern C# code using `LibraryImport` attributes and type-safe unsafe pointers for struct parameters.

## Features

- **Modern C# Code Generation**: Uses `LibraryImport` (not deprecated `DllImport`)
- **Per-Library Binding**: Each header can specify its own library name for correct P/Invoke attributes
- **Type-Safe Pointers**: Generates typed pointers (`SDL_Window*`) instead of generic `nint`
- **Automatic Type Mapping**: Intelligently maps C types to C# equivalents
- **String Handling**: Provides both raw pointer and helper string methods for `char*` returns
- **Struct Generation**: Creates explicit layout structs with proper field offsets
- **Union Support**: Converts C unions to C# structs with `LayoutKind.Explicit` and field offsets
- **Typedef Resolution**: Properly resolves struct-to-struct typedefs through the typedef chain
- **Multi-File Output**: Split bindings into separate files per library with `--multi` flag
- **Include Depth Control**: Process headers with configurable include file depth (default: infinite; see [docs/INCLUDE_DEPTH.md](docs/INCLUDE_DEPTH.md))
- **Include Directory Support**: Specify additional header search paths (see [docs/INCLUDE_DIRECTORIES.md](docs/INCLUDE_DIRECTORIES.md))
- **Opaque Type Support**: Handles opaque struct typedefs (like `SDL_Window`)
- **Missing File Handling**: Fails fast when header files are missing (use `--ignore-missing` to continue)

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** - Internal design and how the generator works
- **[Include Depth](docs/INCLUDE_DEPTH.md)** - How to control which headers are processed
- **[Include Directories](docs/INCLUDE_DIRECTORIES.md)** - Managing header search paths
- **[Multi-File Output](docs/MULTI_FILE_OUTPUT.md)** - Split bindings into separate files per library
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

## Usage

### Command Line

#### Single Library
```bash
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -o SDL3.cs \
  -n SDL \
  -I /usr/include
```

#### Multiple Libraries (Single File)
```bash
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -i /usr/include/libtcod/libtcod.h:libtcod \
  -o Bindings.cs \
  -n GameLibs \
  -I /usr/include
```

#### Multiple Libraries (Multi-File Output)
```bash
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -i /usr/include/libtcod/libtcod.h:libtcod \
  -o ./bindings \
  --multi \
  -n GameLibs \
  -I /usr/include
```

This creates:
- `bindings/bindings.cs` - Assembly attributes and namespace
- `bindings/SDL3.cs` - SDL3-specific bindings
- `bindings/libtcod.cs` - LibTCOD-specific bindings

### Options

- `-i, --input`: Input C header file(s) as `header.h:library` pairs (required, can specify multiple)
- `-o, --output`: Output C# file (optional, defaults to stdout)
- `-n, --namespace`: C# namespace (default: "Bindings")
- `-I, --include-dir`: Additional include directories for clang
- `--include-depth`: Maximum include file depth to process (default: infinite)
- `--ignore-missing`: Continue processing even if some header files are not found
- `--multi`: Split output into multiple files (one per library) in the output directory
- `--clang-path`: Path to libclang library (optional)

### Python API

```python
from cs_binding_generator.generator import CSharpBindingsGenerator

generator = CSharpBindingsGenerator()

# Single file output
output = generator.generate(
    header_library_pairs=[("/usr/include/SDL3/SDL.h", "SDL3")],
    namespace="SDL",
    include_dirs=["/usr/include"]
)
print(output)

# Multi-file output
file_contents = generator.generate(
    header_library_pairs=[
        ("/usr/include/SDL3/SDL.h", "SDL3"),
        ("/usr/include/libtcod/libtcod.h", "libtcod")
    ],
    namespace="GameLibs",
    include_dirs=["/usr/include"],
    multi_file=True,
    output="./bindings"
)
# Returns dict: {"bindings.cs": content, "SDL3.cs": content, "libtcod.cs": content}
```

### Generated Output Example

When processing multiple libraries, each function gets the correct `LibraryImport` attribute:

```csharp
public static unsafe partial class NativeMethods
{
    [LibraryImport("SDL3", EntryPoint = "SDL_Init", StringMarshalling = StringMarshalling.Utf8)]
    public static partial int SDL_Init(uint flags);

    [LibraryImport("libtcod", EntryPoint = "TCOD_init", StringMarshalling = StringMarshalling.Utf8)]
    public static partial void TCOD_init(int w, int h, nuint title);
}
```

## How It Works

### Architecture

1. **Parsing**: Uses libclang to parse C header files into an AST (Abstract Syntax Tree)
2. **Type Discovery**: Pre-scans the AST to identify opaque types (empty struct typedefs)
3. **Code Generation**: Walks the AST and generates C# code for:
   - Enums → C# enums
   - Structs/Unions → C# structs with `[StructLayout(LayoutKind.Explicit)]`
   - Functions → C# static partial methods with `[LibraryImport]`
   - Opaque types → Empty C# structs for type-safe handles

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
typedef struct SDL_Window SDL_Window;

SDL_Window* SDL_CreateWindow(const char* title, int x, int y, int w, int h);
void SDL_DestroyWindow(SDL_Window* window);
const char* SDL_GetWindowTitle(SDL_Window* window);
```

Output C#:
```csharp
public struct SDL_Window
{
}

public static unsafe partial class NativeMethods
{
    [LibraryImport("SDL3", EntryPoint = "SDL_CreateWindow", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial SDL_Window* SDL_CreateWindow(string title, int x, int y, int w, int h);

    [LibraryImport("SDL3", EntryPoint = "SDL_DestroyWindow", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial void SDL_DestroyWindow(SDL_Window* window);

    [LibraryImport("SDL3", EntryPoint = "SDL_GetWindowTitle", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial nuint SDL_GetWindowTitle(SDL_Window* window);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static string? SDL_GetWindowTitleString(SDL_Window* window)
    {
        var ptr = SDL_GetWindowTitle(window);
        return ptr == 0 ? null : Marshal.PtrToStringUTF8((nint)ptr);
    }
}
```

## Testing

The project includes comprehensive tests using pytest:

```bash
# Run all tests
bash run_tests.sh

# Or use pytest directly
pytest tests/ -v

# Run specific test
pytest tests/test_generator.py::TestCSharpBindingsGenerator::test_opaque_types_with_pointers -v
```

## Real-World Example: SDL3

This tool was developed and tested by generating bindings for SDL3. The generated `SDL3.cs` file contains:
- ~10,000 lines of C# code
- Full SDL3 API coverage
- Type-safe window, renderer, and other opaque handle types
- Proper struct layouts with field offsets
- String marshalling helpers

To regenerate SDL3 bindings:
```bash
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h \
  -o SDL3.cs \
  -l SDL3 \
  -n SDL \
  -I /usr/include
```

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
│   └── constants.py         # Shared constants
├── tests/
│   ├── test_generator.py
│   ├── test_type_mapper.py
│   └── test_code_generators.py
├── SDL3.cs                  # Example generated output
└── README.md
```

## Limitations

- Variadic functions are not supported (skipped)
- Complex macros are not processed
- Bitfields in structs are not supported
- Function pointers are mapped to `nint`
- Requires manual handling of callbacks

## Contributing

Since this was an AI-assisted project, contributions are welcome! The codebase is designed to be readable and maintainable despite its AI origins.

## License

See LICENSE file for details.

## Acknowledgments

- Built with the power of AI (Claude Sonnet 4.5)
- Uses libclang for C parsing
- Inspired by the need for better SDL3 C# bindings
