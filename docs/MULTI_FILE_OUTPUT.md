# Multi-File Output

The `--multi` flag enables splitting generated bindings into separate files per library, which is useful for large projects with multiple native libraries.

## Usage

```bash
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -i /usr/include/libtcod/libtcod.h:libtcod \
  -o ./output \
  --multi \
  -n GameLibs
```

## Generated Files

When using `--multi`, the output directory contains:

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

### Regeneration Scripts
Create per-library regeneration scripts:
```bash
# regenerate_sdl3.sh
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -o ./Bindings \
  --multi \
  -n MyProject.Native

# regenerate_all.sh  
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -i /usr/include/libtcod/libtcod.h:libtcod \
  -i /usr/include/freetype2/freetype/freetype.h:freetype \
  -o ./Bindings \
  --multi \
  -n MyProject.Native \
  -I /usr/include/freetype2
```

## Comparison: Single vs Multi-File

| Aspect | Single File | Multi-File |
|--------|------------|------------|
| **File Count** | 1 large file | Multiple focused files |
| **Navigation** | Search within file | Navigate between files |
| **Build Speed** | Slower for large bindings | Faster parallel compilation |
| **Organization** | All in one place | Separated by library |
| **Regeneration** | All-or-nothing | Per-library possible |
| **Code Reviews** | Large diffs | Focused diffs |
| **Memory Usage** | High during compilation | Lower per file |

Choose multi-file output when:
- Working with multiple libraries (2+)
- Bindings are large (>1000 lines per library)
- Build performance is important
- Code organization and maintenance matter

Choose single-file output when:
- Using a single library
- Bindings are small
- Simplicity is preferred
- Legacy compatibility needed