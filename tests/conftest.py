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
