# Multi-File Output

The generator automatically creates separate files for each library defined in your XML configuration. This is useful for large projects with multiple native libraries.

## Configuration

```xml
<bindings>
    <library name="SDL3" namespace="GameLibs">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>

    <library name="libtcod" namespace="GameLibs">
        <include file="/usr/include/libtcod/libtcod.h"/>
    </library>
</bindings>
```

```bash
cs_binding_generator --config cs-bindings.xml --output ./Generated
```

## Generated Files

The output directory contains:

### `bindings.cs`
Contains shared assembly attributes and namespace declaration:
```csharp
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.Marshalling;
using System.Runtime.CompilerServices;

[assembly: System.Runtime.CompilerServices.DisableRuntimeMarshalling]

namespace GameLibs;
```

### Per-Library Files
Each library gets its own file (e.g., `SDL3.cs`, `libtcod.cs`) containing:
- Enums specific to that library
- Structs/unions specific to that library  
- Functions with correct `LibraryImport` attributes

Example `SDL3.cs`:
```csharp
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.Marshalling;
using System.Runtime.CompilerServices;

namespace GameLibs;

public enum SDL_InitFlags
{
    SDL_INIT_TIMER = 0x00000001,
    SDL_INIT_AUDIO = 0x00000010,
    // ...
}

public static unsafe partial class NativeMethods
{
    [LibraryImport("SDL3", EntryPoint = "SDL_Init", StringMarshalling = StringMarshalling.Utf8)]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    public static partial int SDL_Init(uint flags);
    // ...
}
```

## Benefits

### Organization
- **Clear separation**: Each library's bindings are in separate files
- **Easier navigation**: Developers can focus on specific library APIs
- **Reduced conflicts**: Less likely to have naming conflicts between libraries

### Build Performance
- **Partial compilation**: Only recompile changed library bindings
- **Parallel compilation**: C# compiler can process files in parallel
- **Reduced memory usage**: Smaller individual files use less memory during compilation

### Maintenance
- **Selective regeneration**: Regenerate bindings for specific libraries only
- **Version tracking**: Easier to track which library versions were used
- **Code reviews**: Smaller, focused diffs when libraries change

## Assembly Attribute Handling

The `DisableRuntimeMarshalling` assembly attribute can only appear once per assembly. The multi-file generator:

1. **Isolates the attribute** in `bindings.cs` 
2. **Excludes it** from library-specific files
3. **Prevents duplicate attribute errors** during compilation

## Best Practices

### Directory Structure
```
YourProject/
├── Bindings/
│   ├── bindings.cs          # Assembly attributes
│   ├── SDL3.cs              # SDL3 library
│   ├── libtcod.cs          # LibTCOD library
│   └── freetype.cs         # FreeType library
└── YourProject.csproj
```

### Project File
Include all generated files in your `.csproj`:
```xml
<ItemGroup>
  <Compile Include="Bindings/*.cs" />
</ItemGroup>
```

### Regeneration Script
Create a regeneration script:
```bash
#!/bin/bash
# regenerate_bindings.sh
cs_binding_generator \
  --config cs-bindings.xml \
  --output ./Bindings
```

Or with custom config per environment:
```bash
# regenerate_dev.sh
cs_binding_generator --config cs-bindings-dev.xml --output ./Bindings

# regenerate_prod.sh
cs_binding_generator --config cs-bindings-prod.xml --output ./Bindings
```

## Benefits of Multi-File Output

The generator always uses multi-file output (one file per library), which provides:

| Benefit | Description |
|---------|-------------|
| **Organization** | Each library's bindings in separate files |
| **Navigation** | Easy to find specific library APIs |
| **Build Speed** | Faster parallel compilation |
| **Maintenance** | Focused, smaller files are easier to review |
| **Code Reviews** | Changes to one library don't affect others |
| **Memory Usage** | Lower per-file compilation memory footprint |

## Single Library Projects

Even with a single library, the output is split into two files:
- `bindings.cs` - Assembly attributes (shared)
- `yourlibrary.cs` - Your library's bindings

This keeps the assembly-level configuration separate from the generated code.