#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/libtcod.cs"

echo "Regenerating TCod C# bindings..."
echo "Output file: $OUTPUT_FILE"
echo ""

python3 "$PROJECT_ROOT/cs_binding_generator/main.py" \
    -i /usr/include/libtcod/libtcod.h:libtcod \
    -i /usr/include/SDL3/SDL.h:SDL3 \
    -o "$OUTPUT_FILE" \
    -n TCod \
    -I /usr/include/libtcod \
    -I /usr/include/SDL3 \
    -I /usr/include

echo ""
echo "✓ libtcod.cs regenerated successfully"
wc -l "$OUTPUT_FILE" | awk '{print "  Generated: " $1 " lines"}'
