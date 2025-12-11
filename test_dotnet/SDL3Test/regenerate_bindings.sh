#!/bin/bash

# Script to regenerate SDL3 C# bindings
# This will generate bindings from the SDL3 headers installed on the system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/SDL3.cs"
PROJECT_ROOT="$SCRIPT_DIR/../.."

echo "Regenerating SDL3 C# bindings..."
echo "Output file: $OUTPUT_FILE"
echo ""

# Generate bindings by calling main.py directly (no dependencies needed)
python3 "$PROJECT_ROOT/cs_binding_generator/main.py" \
    -i /usr/include/SDL3/SDL.h \
    -l SDL3 \
    -o "$OUTPUT_FILE" \
    -I /usr/include \
    -I /usr/lib/clang/21/include

echo ""
echo "✓ SDL3.cs regenerated successfully"
echo "  Generated: $(wc -l < "$OUTPUT_FILE") lines"
