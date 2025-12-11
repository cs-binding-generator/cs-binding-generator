# Include Depth Control

The C# Bindings Generator allows you to control how deep into the include hierarchy to generate bindings using the `--include-depth` parameter.

## Overview

By default (`--include-depth 0`), the generator only processes definitions from the input header files you specify. With include depth control, you can also generate bindings for types and functions defined in included headers.

## Include Depth Levels

- **Depth 0** (default): Only process the input header file(s)
- **Depth 1**: Process input files + their direct includes
- **Depth 2**: Process input files + includes + includes of those includes
- **Depth N**: Process up to N levels deep in the include hierarchy

## Usage

### Command Line

```bash
# Only process main.h (default behavior)
cs-binding-generator -i main.h -l mylib --include-depth 0

# Process main.h and files it directly includes
cs-binding-generator -i main.h -l mylib --include-depth 1 -I ./include

# Process up to 2 levels of includes
cs-binding-generator -i main.h -l mylib --include-depth 2 -I ./include
```

### Programmatic Usage

```python
from cs_binding_generator import CSharpBindingsGenerator

generator = CSharpBindingsGenerator("mylib")
output = generator.generate(
    header_files=["main.h"],
    output_file="Bindings.cs",
    include_dirs=["./include"],
    include_depth=1  # Process direct includes
)
```

## Example

**Project Structure:**
```
project/
├── include/
│   ├── base.h          # Level 2 (included by common.h)
│   └── common.h        # Level 1 (included by main.h)
└── main.h              # Level 0 (input file)
```

**include/base.h:**
```c
#ifndef BASE_H
#define BASE_H

typedef struct BaseType {
    int value;
} BaseType;

#endif
```

**include/common.h:**
```c
#ifndef COMMON_H
#define COMMON_H

#include "base.h"

typedef struct CommonType {
    BaseType base;
    int extra;
} CommonType;

#endif
```

**main.h:**
```c
#include "common.h"

typedef struct MainType {
    CommonType common;
} MainType;

void process(MainType* data);
```

### Depth 0 (Default)

```bash
cs-binding-generator -i main.h -I ./include -l mylib --include-depth 0
```

**Generated bindings include:**
- ✅ `MainType` struct
- ✅ `process()` function
- ❌ `CommonType` struct (in common.h)
- ❌ `BaseType` struct (in base.h)

### Depth 1

```bash
cs-binding-generator -i main.h -I ./include -l mylib --include-depth 1
```

**Generated bindings include:**
- ✅ `MainType` struct
- ✅ `process()` function
- ✅ `CommonType` struct (directly included)
- ❌ `BaseType` struct (included by common.h, not main.h)

### Depth 2

```bash
cs-binding-generator -i main.h -I ./include -l mylib --include-depth 2
```

**Generated bindings include:**
- ✅ `MainType` struct
- ✅ `process()` function
- ✅ `CommonType` struct
- ✅ `BaseType` struct (2 levels deep)

## When to Use Include Depth

### Depth 0 (Default)
Use when you want tight control over what gets generated. You'll manually specify each header file that should have bindings generated.

**Pros:**
- Precise control
- Smaller output files
- No unwanted types

**Cons:**
- Must list all files manually
- May miss dependencies

### Depth 1+
Use when:
- Working with library headers that use many internal includes
- You want comprehensive bindings for an entire library
- The library has a clear public API header that includes implementation headers

**Pros:**
- Automatic discovery of types
- Complete bindings for complex libraries
- Less manual work

**Cons:**
- May include system headers or internal types you don't want
- Larger output files
- Possible name conflicts

## Tips

1. **Start with depth 0** and only increase if needed
2. **Use include directories** (`-I`) to ensure headers are found
3. **Review the output** - the generator prints which files it processes:
   ```
   Processing 3 file(s) (depth 1):
     [depth 0] main.h
     [depth 1] common.h
   ```
4. **Combine with selective input files** - specify multiple input files at depth 0 for precise control

## System Headers

The generator processes all includes up to the specified depth, including system headers (like `<stdio.h>`). To avoid this:

1. Keep depth low (0 or 1)
2. Use header guards to prevent duplication
3. Filter input files carefully
4. Consider processing system types separately if needed
