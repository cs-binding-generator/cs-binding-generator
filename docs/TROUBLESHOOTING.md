# Troubleshooting Guide

Common issues and their solutions when using the C# Binding Generator.

## XML Configuration Issues

### "Configuration file not found"

**Error:**
```
FileNotFoundError: Configuration file not found: cs-bindings.xml
```

**Solution:**
1. Create `cs-bindings.xml` in the current directory
2. Or specify a different config file: `cs_binding_generator --config path/to/config.xml`

### "Expected root element 'bindings'"

**Error:**
```
ValueError: Expected root element 'bindings', got 'library'
```

**Solution:**
Ensure your XML has the correct root element:
```xml
<bindings>
    <library name="mylib">
        <include file="header.h"/>
    </library>
</bindings>
```

### "Library element missing 'name' attribute"

**Error:**
```
ValueError: Library element missing 'name' attribute
```

**Solution:**
Add the required `name` attribute to your library:
```xml
<library name="SDL3">
    <include file="/usr/include/SDL3/SDL.h"/>
</library>
```

### "Include element missing 'file' attribute"

**Error:**
```
ValueError: Include element in library 'mylib' missing 'file' attribute
```

**Solution:**
Add the `file` attribute to your include:
```xml
<library name="mylib">
    <include file="/path/to/header.h"/>
</library>
```

### "Invalid visibility value"

**Error:**
```
Error: Invalid visibility value 'Private'. Must be 'public' or 'internal'.
```

**Solution:**
Use lowercase `public` or `internal`:
```xml
<bindings visibility="internal">
    <!-- ... -->
</bindings>
```

### "Rename element missing 'from' or 'to' attribute"

**Error:**
```
ValueError: Rename element missing 'from' or 'to' attribute
```

**Solution:**
Ensure both `from` and `to` attributes are present:
```xml
<rename from="SDL_" to=""/>
<rename from="SDL_(.*)" to="$1" regex="true"/>
```

### "Remove element missing 'pattern' attribute"

**Error:**
```
ValueError: Remove element missing 'pattern' attribute
```

**Solution:**
Add the `pattern` attribute:
```xml
<remove pattern="SDL_malloc"/>
<remove pattern=".*_internal" regex="true"/>
```

### "Constants element missing 'name' attribute"

**Error:**
```
ValueError: Constants element missing 'name' attribute
```

**Solution:**
Add both `name` and `pattern` attributes:
```xml
<constants name="WindowFlags" pattern="SDL_WINDOW_.*" type="ulong" flags="true"/>
```

### Regex Pattern Not Working

**Problem:** Rename or remove pattern isn't matching expected identifiers.

**Solution:**
1. Ensure `regex="true"` is set:
   ```xml
   <rename from="SDL_(.*)" to="$1" regex="true"/>
   ```

2. Test your regex pattern separately

3. Remember that simple renames are applied before regex renames

4. Check for escaping issues (use `\` for special regex characters):
   ```xml
   <rename from="prefix_(.*)_suffix" to="$1" regex="true"/>
   ```

### Renaming Not Applied

**Problem:** Generated code still has original C names.

**Solution:**
1. Verify renames are defined before the library:
   ```xml
   <bindings>
       <rename from="SDL_(.*)" to="$1" regex="true"/>
       <library name="SDL3">...</library>
   </bindings>
   ```

2. Remember that renames are global and apply to all libraries

3. Check if removals are filtering out the renamed items

### Constants Not Generated

**Problem:** Expected enum not appearing in generated code.

**Solution:**
1. Verify the pattern matches your macros:
   ```xml
   <constants name="WindowFlags" pattern="SDL_WINDOW_.*"/>
   ```

2. Check that macros have numeric values (hex, octal, or decimal)

3. Macros with expressions like `(1 << 0)` are not currently supported

4. Ensure headers containing the macros are being processed

## Build Errors

### "Cannot use unsafe code without AllowUnsafeBlocks"

**Error:**
```
error CS0227: Unsafe code may only appear if compiling with /unsafe
```

**Solution:**
Add `<AllowUnsafeBlocks>true</AllowUnsafeBlocks>` to your `.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
  </PropertyGroup>
</Project>
```

### "Invalid token '*' in member declaration"

**Error:**
```
error CS1519: Invalid token '*' in a member declaration
```

**Cause:** Struct contains pointers but isn't marked as `unsafe`.

**Solution:** This should be automatically handled by the generator. If you see this error:
1. Regenerate bindings with the latest version
2. Check that all structs are marked as `unsafe`

### "Type or namespace 'wchar_t' could not be found"

**Error:**
```
error CS0246: The type or namespace name 'wchar_t' could not be found
```

**Cause:** The generator is processing types it shouldn't (like platform-specific types).

**Solution:**
1. Reduce `--include-depth` to limit what's processed
2. Add `wchar_t` mapping to type mapper (if needed for your platform)
3. Filter out system headers

## Multiple Libraries

### Using Different Libraries

The generator supports multiple libraries in the XML configuration:

```xml
<bindings>
    <library name="SDL3">
        <include file="/usr/include/SDL3/SDL.h"/>
    </library>

    <library name="libtcod">
        <include file="/usr/include/libtcod/libtcod.h"/>
    </library>
</bindings>
```

**Generated output:**
```csharp
[LibraryImport("SDL3", EntryPoint = "SDL_Init", ...)]
public static partial int SDL_Init(uint flags);

[LibraryImport("libtcod", EntryPoint = "TCOD_init", ...)]
public static partial void TCOD_init(int w, int h, nuint title);
```

### Common Issues

**Problem:** All functions show wrong library name
**Solution:** Check the `name` attribute in your `<library>` elements

**Problem:** Mixed functions in wrong libraries
**Solution:** Verify which header files are included in each library

## Generation Issues

### Empty Output File

**Symptom:** Generated file only contains namespace and using statements.

**Causes:**
1. **Header only contains includes** - Use `--include-depth 1` or higher to process included headers

2. **Header file not found** - Add `<include_directory>` elements to your XML config:
   ```xml
   <bindings>
       <include_directory path="/path/to/headers"/>
       <library name="mylib">
           <include file="mylib.h"/>
       </library>
   </bindings>
   ```

3. **Parse errors** - Check stderr for clang diagnostics

### Missing Types or Functions

**Symptom:** Expected types/functions not in output.

**Debugging steps:**

1. **Check file depth:**
   Run the generator and check the console output showing which files are processed:
   ```
   Processing 5 file(s) (depth 1):
     [depth 0] header.h
     [depth 1] types.h
   ```
   Use `--include-depth` to increase if needed

2. **Verify file is in allowed depth:**
   - Increase `--include-depth` if needed
   - Or explicitly add the header as an input file

3. **Check for parse errors:**
   - Look for "Error in..." messages in stderr
   - Verify all include directories are specified

4. **Variadic functions are skipped:**
   - Functions like `printf(const char*, ...)` can't be mapped
   - This is a known limitation

### Incorrect Types Generated

**Symptom:** Types don't match expected C# types.

**Common issues:**

1. **Pointer to struct mapping:**
   ```c
   void process(struct Foo* ptr);
   ```
   Should generate:
   ```csharp
   public static partial void process(Foo* ptr);
   ```
   
   If you see `nint` instead, regenerate with latest version.

2. **String handling:**
   ```c
   const char* get_name();  // Returns string
   void set_name(const char* name);  // Takes string
   ```
   Should generate:
   ```csharp
   // Return type: raw pointer
   public static partial nuint get_name();
   // Helper method for string
   public static string? get_nameString();
   
   // Parameter: marshalled string
   public static partial void set_name(string name);
   ```

3. **Bool marshalling:**
   Should automatically add `[MarshalAs(UnmanagedType.I1)]`

## Runtime Errors

### DllNotFoundException

**Error:**
```
System.DllNotFoundException: Unable to load DLL 'mylibrary'
```

**Solutions:**

1. **Linux**: Add library to LD_LIBRARY_PATH
   ```bash
   export LD_LIBRARY_PATH=/path/to/lib:$LD_LIBRARY_PATH
   ```

2. **Windows**: Copy DLL to application directory or add to PATH

3. **macOS**: Use DYLD_LIBRARY_PATH or install via Homebrew

4. **Check library name:**
   ```bash
   # Linux
   ldd myapp | grep mylib
   
   # macOS  
   otool -L myapp | grep mylib
   ```

### AccessViolationException

**Error:**
```
System.AccessViolationException: Attempted to read or write protected memory
```

**Causes:**

1. **Null pointer passed to native function**
   ```csharp
   // Wrong
   SDL_Window* window = null;
   SDL_DestroyWindow(window);  // Crash!
   
   // Correct
   if (window != null)
       SDL_DestroyWindow(window);
   ```

2. **Using pointer after it's been freed**
   ```csharp
   var window = SDL_CreateWindow(...);
   SDL_DestroyWindow(window);
   SDL_SetWindowTitle(window, "title");  // Crash! window is dangling
   ```

3. **Struct layout mismatch**
   - Regenerate bindings if struct definition changed
   - Ensure generated layout matches native library

### BadImageFormatException

**Error:**
```
System.BadImageFormatException: An attempt was made to load a program with an incorrect format
```

**Cause:** Architecture mismatch (x64 app trying to load x86 DLL or vice versa).

**Solution:**
```xml
<PropertyGroup>
  <PlatformTarget>x64</PlatformTarget>  <!-- or x86 -->
</PropertyGroup>
```

## libclang Issues

### "libclang not found"

**Error:**
```
Exception: libclang not found
```

**Solutions:**

**Ubuntu/Debian:**
```bash
sudo apt install libclang-dev python3-clang
```

**macOS:**
```bash
brew install llvm
export DYLD_LIBRARY_PATH="$(brew --prefix llvm)/lib:$DYLD_LIBRARY_PATH"
```

**Arch Linux:**
```bash
sudo pacman -S clang python-clang
```

**Manual specification:**
```bash
cs_binding_generator --clang-path /usr/lib/libclang.so ...
```

### Parse Errors

**Symptom:** Errors like "unknown type name" or "expected ';'"

**Solutions:**

1. **Add missing include directories to your XML config:**
   ```xml
   <bindings>
       <include_directory path="./include"/>
       <include_directory path="/opt/custom/include"/>

       <library name="mylib">
           <include file="header.h"/>
       </library>
   </bindings>
   ```
   Note: System paths like `/usr/include` are found automatically

2. **Check header file syntax:**
   ```bash
   # Test with clang directly
   clang -fsyntax-only header.h
   ```

3. **Verify include guards:**
   Make sure headers have proper include guards to prevent multiple inclusion

## Performance Issues

### Slow Generation

**Symptom:** Generation takes a very long time.

**Solutions:**

1. **Reduce include depth:**
   ```bash
   # Instead of depth 10
   --include-depth 1  # Usually sufficient
   ```

2. **Limit input files:**
   Only specify headers you actually need

3. **Check for circular includes:**
   May cause excessive processing

### Large Output Files

**Symptom:** Generated C# file is huge.

**Solutions:**

1. **Reduce include depth** to avoid processing too many headers

2. **Use separate libraries in your XML config:**
   ```xml
   <bindings>
       <library name="mylib_video">
           <include file="video.h"/>
       </library>

       <library name="mylib_audio">
           <include file="audio.h"/>
       </library>
   </bindings>
   ```
   This generates separate files: `mylib_video.cs` and `mylib_audio.cs`

## Test Failures

### "FileNotFoundError: 'cs_binding_generator'"

**Error during tests:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'cs_binding_generator'
```

**Cause:** CLI tool not installed.

**Solution:**
```bash
# Install in development mode
pip install -e .

# Or run tests without CLI tests
pytest tests/ -k "not test_sdl3_generates_valid_csharp"
```

## Multi-File Output Issues

### "Duplicate 'DisableRuntimeMarshalling' attribute"

**Error:**
```
error CS0579: Duplicate 'System.Runtime.CompilerServices.DisableRuntimeMarshalling' attribute
```

**Cause:** The assembly attribute appears in multiple generated files.

**Solution:**
This should be automatically handled by creating a separate `bindings.cs` file. If you see this error:
1. Ensure you're using the latest version of the generator
2. Check that `bindings.cs` contains the assembly attribute
3. Verify other `.cs` files don't contain the assembly attribute
4. Regenerate all bindings

### Output Directory Issues

**Problem:** Not sure where files are being generated.

**Solution:**
Use the `-o` or `--output` flag to specify the output directory:
```bash
cs_binding_generator --config cs-bindings.xml --output ./Generated
```

If not specified, files are generated in the current directory.

### Empty Files Generated

**Issue:** Some library files are empty or only contain namespace/usings.

**Cause:** No functions, structs, or enums were found for that library.

**Solutions:**
1. **Check library name:** Ensure the library name in `header.h:library` matches what you expect
2. **Verify parsing:** Look at the console output to see what's being processed
3. **Check include depth:** The content might be in included headers (`--include-depth`)

### Missing Library Files

**Issue:** Expected library files weren't generated.

**Debugging steps:**
1. Check console output for which libraries were detected
2. Verify header files were parsed successfully  
3. Ensure the header:library mapping is correct
4. Check if the library has any exportable symbols

### File Permissions Issues

**Error:**
```
PermissionError: [Errno 13] Permission denied: './output/SDL3.cs'
```

**Solutions:**
1. Ensure output directory is writable
2. Close any editors that might have the files open
3. Check file permissions in the output directory

## Getting Help

If you encounter an issue not covered here:

1. **Check the examples:**
   - Review `INCLUDE_DEPTH.md`
   - Review `INCLUDE_DIRECTORIES.md`
   - Look at SDL3 generation as a reference

2. **Enable verbose output:**
   The generator prints diagnostic information about which files are processed

3. **Test with minimal example:**
   Create a simple test header to isolate the issue

4. **Check libclang version:**
   ```bash
   clang --version
   ```
   Ensure you have a recent version (15+)

5. **Review test cases:**
   The `tests/` directory has many examples of correct usage

6. **File an issue:**
   Include:
   - Command used
   - Header file (or minimal reproduction)
   - Error message
   - Platform and clang version
