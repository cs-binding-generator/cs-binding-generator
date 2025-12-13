#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR"

echo "Regenerating bindings..."
echo "Config file: $SCRIPT_DIR/cs-bindings.xml"
echo "Output directory: $OUTPUT_DIR"
echo ""

python3 "$PROJECT_ROOT/cs_binding_generator/main.py" \
    --config "$SCRIPT_DIR/cs-bindings.xml" \
    -o "$OUTPUT_DIR"

echo ""
echo "✓ Multi-file bindings regenerated successfully"
echo "Generated files:"
ls -la "$OUTPUT_DIR"/*.cs | awk '{print "  " $9 ": " $5 " bytes"}'
