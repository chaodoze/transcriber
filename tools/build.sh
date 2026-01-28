#!/bin/bash
# Build the FetchTranscript helper tool
# Requires macOS 15.5+ and Xcode Command Line Tools

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building FetchTranscript..."

clang -Wno-objc-method-access \
  -framework Foundation \
  -F/System/Library/PrivateFrameworks \
  -framework AppleMediaServices \
  FetchTranscript.m -o FetchTranscript

echo "Build complete: $SCRIPT_DIR/FetchTranscript"
echo ""
echo "Test with: ./FetchTranscript <episode_id> --cache-bearer-token"
