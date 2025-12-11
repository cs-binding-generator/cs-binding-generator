"""
Pytest configuration and fixtures
"""

import pytest
from pathlib import Path
import tempfile


@pytest.fixture
def temp_header_file():
    """Create a temporary C header file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.h', delete=False) as f:
        f.write("""
// Simple test header
typedef struct Point {
    int x;
    int y;
} Point;

enum Status {
    OK = 0,
    ERROR = 1,
    PENDING = 2
};

int add(int a, int b);
void* get_data();
const char* get_name();
""")
        path = f.name
    
    yield path
    
    # Cleanup
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def complex_header_file():
    """Create a more complex C header file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.h', delete=False) as f:
        f.write("""
// Complex test header
typedef struct Vector3 {
    float x;
    float y;
    float z;
} Vector3;

typedef struct Matrix {
    float data[16];
} Matrix;

enum Color {
    RED = 0xFF0000,
    GREEN = 0x00FF00,
    BLUE = 0x0000FF
};

typedef enum {
    MODE_NORMAL,
    MODE_DEBUG,
    MODE_RELEASE
} BuildMode;

// Function declarations
void init_engine(const char* config_path);
Vector3* create_vector(float x, float y, float z);
void destroy_vector(Vector3* vec);
float dot_product(Vector3* a, Vector3* b);
Matrix* get_identity_matrix();
unsigned long long get_timestamp();
""")
        path = f.name
    
    yield path
    
    # Cleanup
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def header_with_include(tmp_path):
    """Create header files with #include directive"""
    # Create an include directory
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    
    # Create a common header in include directory
    common_header = include_dir / "common.h"
    common_header.write_text("""
#ifndef COMMON_H
#define COMMON_H

typedef struct Config {
    int width;
    int height;
    int depth;
} Config;

#define MAX_SIZE 1024

#endif
""")
    
    # Create main header that includes common.h
    main_header = tmp_path / "main.h"
    main_header.write_text("""
#include "common.h"

typedef struct Window {
    Config config;
    char title[MAX_SIZE];
} Window;

void init_window(Window* win);
""")
    
    return {
        'main': str(main_header),
        'include_dir': str(include_dir),
        'common': str(common_header)
    }


@pytest.fixture
def nested_includes(tmp_path):
    """Create nested include hierarchy for testing include depth"""
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    
    # Level 2: Deepest header
    level2_header = include_dir / "level2.h"
    level2_header.write_text("""
#ifndef LEVEL2_H
#define LEVEL2_H

typedef struct DeepStruct {
    int deep_value;
} DeepStruct;

void level2_function();

#endif
""")
    
    # Level 1: Middle header that includes level2
    level1_header = include_dir / "level1.h"
    level1_header.write_text("""
#ifndef LEVEL1_H
#define LEVEL1_H

#include "level2.h"

typedef struct MiddleStruct {
    int middle_value;
    DeepStruct deep;
} MiddleStruct;

void level1_function();

#endif
""")
    
    # Level 0: Root header that includes level1
    root_header = tmp_path / "root.h"
    root_header.write_text("""
#include "level1.h"

typedef struct RootStruct {
    int root_value;
    MiddleStruct middle;
} RootStruct;

void root_function();
""")
    
    return {
        'root': str(root_header),
        'include_dir': str(include_dir),
        'level1': str(level1_header),
        'level2': str(level2_header)
    }


@pytest.fixture
def opaque_types_header():
    """Create a header with opaque types (like SDL_Window)"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.h', delete=False) as f:
        f.write("""
// Opaque types header (like SDL)
typedef struct SDL_Window SDL_Window;
typedef struct SDL_Renderer SDL_Renderer;

// Functions that use opaque types
SDL_Window* SDL_CreateWindow(const char* title, int x, int y, int w, int h, unsigned int flags);
void SDL_DestroyWindow(SDL_Window* window);
const char* SDL_GetWindowTitle(SDL_Window* window);
int SDL_SetWindowTitle(SDL_Window* window, const char* title);
SDL_Renderer* SDL_CreateRenderer(SDL_Window* window);
void SDL_RenderPresent(SDL_Renderer* renderer);
""")
        path = f.name
    
    yield path
    
    # Cleanup
    Path(path).unlink(missing_ok=True)
