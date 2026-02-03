#!/bin/bash
# Manager PC Connection Test Wrapper
#
# Usage:
#   ./test_connections.sh              - Run all tests
#   ./test_connections.sh --camera     - Test camera only
#   ./test_connections.sh --artiq      - Test ARTIQ only
#   ./test_connections.sh --labview    - Test LabVIEW only
#   ./test_connections.sh --verbose    - Detailed output
#

echo "============================================================"
echo "   Manager PC Connection Test Suite"
echo "============================================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed or not in PATH"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Run the test script with all arguments passed through
python3 test_connections.py "$@"

# Exit with same code
exit $?
