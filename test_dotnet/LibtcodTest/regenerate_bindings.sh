#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR"

echo "Regenerating TCod C# bindings with multi-file output..."
echo "Output directory: $OUTPUT_DIR"
echo ""

python3 "$PROJECT_ROOT/cs_binding_generator/main.py" \
    -i /usr/include/libtcod/libtcod.h:libtcod \
    -i /usr/include/SDL3/SDL.h:SDL3 \
    -o "$OUTPUT_DIR" \
    --multi \
    -n TCod \
    -I /usr/include/libtcod \
    -I /usr/include/SDL3 \
    -I /usr/include

echo ""
echo "✓ Multi-file bindings regenerated successfully"
echo "Generated files:"
ls -la "$OUTPUT_DIR"/*.cs | awk '{print "  " $9 ": " $5 " bytes"}'
