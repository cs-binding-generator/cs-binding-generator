"""
Test fixtures - sample C header files for testing
"""

SIMPLE_HEADER = """
// Simple test header
typedef struct Point {
    int x;
    int y;
} Point;

enum Status {
    OK = 0,
    ERROR = 1
};

int add(int a, int b);
"""

COMPLEX_HEADER = """
// Complex test header
typedef struct Vector3 {
    float x;
    float y;
    float z;
} Vector3;

typedef enum {
    MODE_A,
    MODE_B,
    MODE_C
} Mode;

void* allocate_buffer(unsigned long size);
const char* get_error_message();
void free_buffer(void* buffer);
"""

POINTER_TYPES_HEADER = """
// Test various pointer types
struct Data;

void process_data(struct Data* data);
char* get_string();
void set_string(const char* str);
int* get_array();
void** get_ptr_array();
"""

FUNCTION_VARIANTS_HEADER = """
// Test various function signatures
void no_params();
int one_param(float x);
double many_params(int a, float b, char c, long long d);
void* return_pointer();
const char* return_string();
"""

EDGE_CASES_HEADER = """
// Edge cases
typedef struct {
    int value;
} AnonymousStruct;

enum {
    ANON_VALUE = 42
};

// Unnamed parameters
void unnamed_params(int, float);
"""
