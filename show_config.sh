#!/bin/bash
# Quick script to show current config

echo ""
echo "CURRENT CONFIG.YAML CONTENT (model section)"
echo ""
echo ""

if [ -f "config.yaml" ]; then
 # Show first 25 lines which includes the model config
 head -n 25 config.yaml
 echo ""
 echo ""
 echo "KEY SETTINGS:"
 echo ""
 echo ""
 echo "Repo ID:"
 grep "repo_id:" config.yaml | head -1
 echo ""
 echo "Filename:"
 grep "filename:" config.yaml | head -1
 echo ""
 
 if grep -q "bartowski" config.yaml; then
 echo " CORRECT - Using bartowski repos "
 else
 echo " WRONG - NOT using bartowski! "
 fi
else
 echo " config.yaml not found in current directory!"
 echo "Current directory: $(pwd)"
fi

echo ""
echo ""
