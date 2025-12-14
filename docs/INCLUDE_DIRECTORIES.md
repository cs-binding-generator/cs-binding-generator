# Include Directories

The C# Bindings Generator needs to know where to find header files referenced by `#include` directives. Include directories are specified in the XML configuration file using `<include_directory>` elements.

## Why Include Directories Matter

When a C header file contains `#include "common.h"` or `#include <SDL3/SDL.h>`, the compiler needs to know where to find these files. Include directories tell libclang where to search for header files.

Without proper include directories, you'll get parse errors and incomplete bindings.

## Configuration

Include directories are specified in the XML configuration file.

**Note:** System include paths like `/usr/include` are automatically detected by clang and do not need to be specified.

### Global Include Directories

```xml
<bindings>
    <!-- Global include directories apply to all libraries -->
    <!-- Note: /usr/include is found automatically, no need to specify -->
    <include_directory path="./include"/>
    <include_directory path="./vendor/include"/>

    <library name="mylib">
        <include file="mylib.h"/>
    </library>
</bindings>
```

### Library-Specific Include Directories

```xml
<bindings>
    <library name="SDL3">
        <!-- Library-specific include directory -->
        <include_directory path="/usr/include/SDL3"/>
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>

    <library name="customlib">
        <!-- Non-standard library location -->
        <include_directory path="/opt/customlib/include"/>
        <include file="/opt/customlib/include/customlib.h"/>
    </library>
</bindings>
```

### Order Matters

Include directories are searched in the order specified:

```xml
<bindings>
    <!-- ./include is searched first, then /opt/custom -->
    <include_directory path="./include"/>
    <include_directory path="/opt/custom/include"/>

    <library name="mylib">
        <include file="mylib.h"/>
    </library>
</bindings>
```

This allows you to override headers with custom versions by placing your include directories first.

## Example

**Project Structure:**
```
project/
├── include/
│   └── common.h       # Shared type definitions
├── mylib.h            # Main header
└── cs-bindings.xml    # Configuration file
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

**cs-bindings.xml:**
```xml
<bindings>
    <!-- Tell the generator where to find headers -->
    <include_directory path="./include"/>

    <library name="mylib" namespace="MyApp.Interop">
        <include file="./mylib.h"/>
    </library>
</bindings>
```

**Generate Bindings:**
```bash
cs_binding_generator  # Uses cs-bindings.xml
```

**Generated Output:**
```csharp
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.Marshalling;

namespace MyApp.Interop;

[StructLayout(LayoutKind.Explicit)]
public struct Config
{
    [FieldOffset(0)] public int width;
    [FieldOffset(4)] public int height;
}

[StructLayout(LayoutKind.Explicit)]
public unsafe struct Window
{
    [FieldOffset(0)] public Config config;
    [FieldOffset(8)] public fixed byte title[256];
}

public static unsafe partial class NativeMethods
{
    [LibraryImport("mylib", EntryPoint = "init_window", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial void init_window(Window* win);

    [LibraryImport("mylib", EntryPoint = "close_window", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial void close_window(Window* win);
}
```

## Common Include Directory Patterns

### Local Project Headers
```xml
<include_directory path="./include"/>
<include_directory path="./src"/>
```

### Homebrew Libraries (macOS)
```xml
<!-- Homebrew installs to non-standard locations -->
<include_directory path="/opt/homebrew/include"/>
```

### Custom Installation Paths
```xml
<include_directory path="/opt/mylib/include"/>
<include_directory path="$HOME/.local/include"/>
```

### Typical Project Setup
```xml
<bindings>
    <!-- Project-specific headers -->
    <include_directory path="./include"/>
    <include_directory path="./vendor/include"/>

    <!-- Non-standard library locations -->
    <include_directory path="/opt/local/include"/>

    <!-- Note: /usr/include, /usr/local/include are found automatically -->

    <library name="mylib">
        <include file="./mylib.h"/>
    </library>
</bindings>
```

## Troubleshooting

### "Header file not found" errors

1. **Check the include path**: Make sure the directory containing the header exists
2. **Use absolute paths**: Try using absolute paths instead of relative
3. **Verify file permissions**: Ensure the header files are readable
4. **Check for typos**: Verify the header filename matches exactly (case-sensitive)

### Parse errors in generated output

This usually means libclang couldn't find all dependencies. Add the missing include directories:

```xml
<bindings>
    <!-- Add directories where your headers are located -->
    <include_directory path="./include"/>
    <include_directory path="/opt/customlib/include"/>

    <library name="mylib">
        <include file="mylib.h"/>
    </library>
</bindings>
```

**Note:** Clang built-in headers (like `stdint.h`, `stddef.h`) are found automatically.

## Notes

- Include directories are passed to libclang as `-I<directory>` arguments internally
- **System include paths** (`/usr/include`, `/usr/local/include`) are automatically detected by clang - you don't need to specify them
- Paths can be relative (to current directory) or absolute
- Both global and library-specific include directories are supported
- Only specify include directories for non-standard locations (project headers, custom installs, Homebrew, etc.)

## See Also

- [XML Configuration](XML_CONFIG.md) - Complete XML configuration guide
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
