# Include Directories Feature

The C# Bindings Generator now supports include directories, similar to the `-I` flag in C/C++ compilers.

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
- The generator only processes types/functions defined in the input header files
- Types from included headers are resolved but not generated (unless they appear in the input files)
- Multiple `-I` flags can be specified on the command line
