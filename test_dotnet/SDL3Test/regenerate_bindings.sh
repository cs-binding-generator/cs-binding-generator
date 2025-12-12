#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/SDL3.cs"
PROJECT_ROOT="$SCRIPT_DIR/../.."

echo "Regenerating SDL3 C# bindings using XML configuration..."
echo "Config file: $SCRIPT_DIR/cs-bindings.xml"
echo "Output file: $OUTPUT_FILE"
echo ""

python3 "$PROJECT_ROOT/cs_binding_generator/main.py" \
    --config "$SCRIPT_DIR/cs-bindings.xml" \
    -o "$OUTPUT_FILE" \
    -I /usr/include \
    -I /usr/lib/clang/21/include

echo ""
echo "✓ SDL3.cs regenerated successfully"
echo "  Generated: $(wc -l < "$OUTPUT_FILE") lines"
