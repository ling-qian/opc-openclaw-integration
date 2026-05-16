#!/bin/bash
# Deploy OPC-OpenClaw Integration to Railway or Render
# Prerequisites: railway CLI or render CLI installed and logged in

set -e

echo "=== OPC-OpenClaw Integration Deploy ==="

# Detect deployment target
TARGET=${1:-railway}
case $TARGET in
  railway)
    echo "Deploying to Railway..."
    railway up --service opc-openclaw-integration
    ;;
  render)
    echo "Deploying to Render..."
    # Render uses web service creation; assume service exists
    render deploy --service opc-openclaw-integration
    ;;
  *)
    echo "Unknown target: $TARGET. Use 'railway' or 'render'."
    exit 1
    ;;
esac

echo "✅ Deployment triggered. Check dashboard for status."
