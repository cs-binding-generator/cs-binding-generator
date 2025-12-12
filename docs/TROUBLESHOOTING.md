# Troubleshooting Guide

Common issues and their solutions when using the C# Binding Generator.

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

The generator supports specifying different library names for different headers:

```bash
# Each function gets the correct LibraryImport attribute
cs_binding_generator \
  -i /usr/include/SDL3/SDL.h:SDL3 \
  -i /usr/include/libtcod/libtcod.h:libtcod \
  -o GameBindings.cs
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
**Solution:** Use the `header.h:library` format for each input file

**Problem:** Mixed functions in wrong libraries  
**Solution:** Regenerate bindings using separate header:library pairs for each library

## Generation Issues

### Empty Output File

**Symptom:** Generated file only contains namespace and using statements.

**Causes:**
1. **Include depth is 0 and header only has includes**
   ```bash
   # SDL.h only includes other headers, need depth 1
   cs_binding_generator -i SDL.h:SDL3 --include-depth 1
   ```

2. **Header file not found**
   ```bash
   # Add include directories
   cs_binding_generator -i mylib.h:mylib -I /path/to/headers
   ```

3. **Parse errors** - Check stderr for clang diagnostics

### Missing Types or Functions

**Symptom:** Expected types/functions not in output.

**Debugging steps:**

1. **Check file depth:**
   ```bash
   # Run with verbose output to see which files are processed
   cs_binding_generator -i header.h:mylib --include-depth 1
   
   # Look for output like:
   # Processing 5 file(s) (depth 1):
   #   [depth 0] header.h
   #   [depth 1] types.h
   ```

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

1. **Add missing include directories:**
   ```bash
   cs_binding_generator -i header.h:mylib \
     -I /usr/include \
     -I /usr/lib/clang/21/include
   ```

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

2. **Split into multiple files:**
   ```bash
   # Generate separate bindings for different subsystems
   cs_binding_generator -i video.h:mylib -o Video.cs
   cs_binding_generator -i audio.h:mylib -o Audio.cs
   ```

3. **Use partial classes** to organize generated code across files

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
