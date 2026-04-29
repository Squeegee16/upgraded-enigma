#!/bin/bash
# check-go-version.sh
# Run this before docker compose build to find the
# minimum Go version required by all plugins.
#
# Usage: ./check-go-version.sh

echo "=== Checking Go Version Requirements ==="
echo ""

MIN_REQUIRED="1.21"  # Minimum acceptable version

for plugin_dir in plugins/implementations/*/; do
    if [ -f "${plugin_dir}go.mod" ]; then
        REQUIRED=$(grep "^go " "${plugin_dir}go.mod" \
            | awk '{print $2}')
        echo "Plugin: ${plugin_dir}"
        echo "  go.mod requires: Go ${REQUIRED}"
    fi
done

echo ""
echo "Checking GitHub repositories for go.mod versions..."

REPOS=(
    "https://raw.githubusercontent.com/chrissnell/graywolf/main/go.mod"
)

for repo_url in "${REPOS[@]}"; do
    VERSION=$(curl -sf "$repo_url" 2>/dev/null | \
        grep "^go " | awk '{print $2}')
    if [ -n "$VERSION" ]; then
        echo "Remote go.mod: $VERSION ($repo_url)"
        # Compare with minimum
        if [ "$(printf '%s\n' "$VERSION" "$MIN_REQUIRED" | \
            sort -V | head -1)" != "$VERSION" ]; then
            echo "  ⚠ Version $VERSION > minimum $MIN_REQUIRED"
            echo "  Update Dockerfile: ARG GO_VERSION=$VERSION"
        fi
    fi
done

echo ""
echo "Current Dockerfile GO_VERSION:"
grep "ARG GO_VERSION" Dockerfile || echo "  Not found"

echo ""
echo "Recommended: Set ARG GO_VERSION to the highest"
echo "version required by any plugin's go.mod"
