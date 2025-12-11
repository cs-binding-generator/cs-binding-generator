# Include Directories Feature

The C# Bindings Generator supports include directories, similar to the `-I` flag in C/C++ compilers. This is essential for resolving header files that use `#include` directives.

## Why Include Directories Matter

When a C header file contains `#include "common.h"` or `#include <SDL3/SDL.h>`, the compiler needs to know where to find these files. Include directories tell libclang where to search for header files.

Without proper include directories, you'll get parse errors and incomplete bindings.

## Usage

### Single Include Directory

```bash
cs-binding-generator -i mylib.h -I /usr/include -o Bindings.cs -l mylib
```

### Multiple Include Directories

```bash
cs-binding-generator -i mylib.h \
    -I /usr/include \
    -I /usr/local/include \
    -I ./include \
    -o Bindings.cs -l mylib
```

### Order Matters

Include directories are searched in the order specified:
```bash
# ./include is searched first, then /usr/include
cs-binding-generator -i mylib.h -I ./include -I /usr/include
```

This allows you to override system headers with custom versions.

## Example

**Project Structure:**
```
project/
├── include/
│   └── common.h       # Shared type definitions
└── mylib.h            # Main header
```

**include/common.h:**
```c
#ifndef COMMON_H
#define COMMON_H

typedef struct Config {
    int width;
    int height;
} Config;

#endif
```

**mylib.h:**
```c
#include "common.h"

typedef struct Window {
    Config config;
    char title[256];
} Window;

void init_window(Window* win);
void close_window(Window* win);
```

**Generate Bindings:**
```bash
cs-binding-generator \
    -i mylib.h \
    -I ./include \
    -o MyLibBindings.cs \
    -l mylib \
    -n MyApp.Interop
```

**Generated Output:**
```csharp
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.Marshalling;

namespace MyApp.Interop;

[StructLayout(LayoutKind.Sequential)]
public struct Window
{
    public Config config;
    public char[256] title;
}

public static partial class NativeMethods
{
    [LibraryImport("mylib", EntryPoint = "init_window")]
    public static partial void init_window(nint win);

    [LibraryImport("mylib", EntryPoint = "close_window")]
    public static partial void close_window(nint win);
}
```

## Programmatic Usage

```python
from cs_binding_generator import CSharpBindingsGenerator

generator = CSharpBindingsGenerator("mylib")
output = generator.generate(
    header_files=["mylib.h"],
    output_file="Bindings.cs",
    namespace="MyApp.Interop",
    include_dirs=["./include", "/usr/include"]
)
```

## Notes

- Include directories are passed to libclang as `-I<directory>` arguments
- The generator automatically queries clang for system include paths
- Multiple `-I` flags can be specified on the command line
- Paths can be relative or absolute
- The generator respects `--include-depth` when processing included files

## Automatic System Include Detection

The generator automatically detects common system include paths by querying clang:

```python
# Automatically detected (example):
# /usr/lib/clang/21/include
# /usr/local/include
# /usr/include
```

This means you often don't need to specify system paths manually.

## Common Include Directory Patterns

### System Libraries (Linux)
```bash
-I /usr/include
```

### Homebrew Libraries (macOS)
```bash
-I /opt/homebrew/include
```

### Local Project Headers
```bash
-I ./include
-I ./src
```

### Mixed Environment
```bash
cs-binding-generator \
  -i mylib.h \
  -I ./include \              # Project headers
  -I /usr/local/include \     # Local libraries
  -I /usr/include \           # System headers
  -o Bindings.cs \
  -l mylib
```

## Troubleshooting

### "Header file not found" errors

1. **Check the include path**: Make sure the directory containing the header exists
2. **Use absolute paths**: Try using absolute paths instead of relative
3. **Verify file permissions**: Ensure the header files are readable
4. **Check for typos**: Verify the header filename matches exactly (case-sensitive)

### Parse errors in generated output

This usually means libclang couldn't find all dependencies. Add more include directories:

```bash
# Add clang's built-in include directory
-I /usr/lib/clang/$(clang --version | grep -oP '(?<=version )\d+' | head -1)/include
```

## Combining with Include Depth

Include directories and include depth work together:

```bash
cs-binding-generator \
  -i /usr/include/SDL3/SDL.h \
  -I /usr/include \           # Where to find headers
  --include-depth 1 \         # How deep to process them
  -o SDL3.cs \
  -l SDL3
```

The include directories tell libclang where to find files, while include depth controls which of those files get processed for binding generation.
