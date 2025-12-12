#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/FreeType.cs"

echo "Regenerating FreeType C# bindings using XML configuration..."
echo "Config file: $SCRIPT_DIR/cs-bindings.xml"
echo "Output file: $OUTPUT_FILE"
echo ""

python3 "$PROJECT_ROOT/cs_binding_generator/main.py" \
    --config "$SCRIPT_DIR/cs-bindings.xml" \
    -o "$OUTPUT_FILE"

echo ""
echo "✓ FreeType.cs regenerated successfully"
wc -l "$OUTPUT_FILE" | awk '{print "  Generated: " $1 " lines"}'
