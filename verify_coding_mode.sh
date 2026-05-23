#!/bin/bash
# Verify that all coding mode enhancements are in place

echo "════════════════════════════════════════════════════════════════"
echo "  MYTHOS CODING MODE - VERIFICATION CHECKLIST"
echo "════════════════════════════════════════════════════════════════"
echo ""

check_file() {
    if [ -f "$1" ]; then
        size=$(wc -c < "$1" 2>/dev/null)
        echo "✅ $1 (${size} bytes)"
        return 0
    else
        echo "❌ $1 MISSING!"
        return 1
    fi
}

check_in_file() {
    if grep -q "$2" "$1" 2>/dev/null; then
        echo "✅ $1 contains '$2'"
        return 0
    else
        echo "❌ $1 missing '$2'"
        return 1
    fi
}

errors=0

echo "1. CHECKING ENHANCED PROMPTS:"
echo "────────────────────────────────────────────────────────────────"
check_file "prompts/coding.txt" || ((errors++))
check_file "prompts/code_review.txt" || ((errors++))
check_file "prompts/debugging.txt" || ((errors++))
check_file "prompts/default.txt" || ((errors++))
echo ""

echo "2. CHECKING PROMPT CONTENT:"
echo "────────────────────────────────────────────────────────────────"
check_in_file "prompts/coding.txt" "FIVE VERIFICATION" || ((errors++))
check_in_file "prompts/code_review.txt" "FIVE-PASS CODE REVIEW" || ((errors++))
check_in_file "prompts/debugging.txt" "SYSTEMATIC DEBUGGING" || ((errors++))
check_in_file "prompts/default.txt" "CODE QUALITY STANDARDS" || ((errors++))
echo ""

echo "3. CHECKING DOCUMENTATION:"
echo "────────────────────────────────────────────────────────────────"
check_file "CODING_GUIDE.md" || ((errors++))
check_file "CODING_ACTIVATED.txt" || ((errors++))
check_file "FINAL_SUMMARY.md" || ((errors++))
check_file "RUN_THIS.txt" || ((errors++))
echo ""

echo "4. CHECKING UI UPDATES:"
echo "────────────────────────────────────────────────────────────────"
check_in_file "ui/terminal_ui.py" "Enhanced Coding Modes" || ((errors++))
check_in_file "config.yaml" "bartowski" || ((errors++))
echo ""

echo "5. CHECKING HELPER SCRIPTS:"
echo "────────────────────────────────────────────────────────────────"
check_file "test_coding.sh" || ((errors++))
check_file "run_chat.sh" || ((errors++))
echo ""

echo "════════════════════════════════════════════════════════════════"
if [ $errors -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED!"
    echo ""
    echo "🔥 ELITE CODING MODE IS READY!"
    echo ""
    echo "Start with:"
    echo "  source venv/bin/activate"
    echo "  python3 main.py --mode chat"
    echo "  /system coding"
    echo ""
else
    echo "⚠️  $errors CHECK(S) FAILED"
    echo ""
    echo "Some files may be missing or incomplete."
    echo "Review the output above for details."
    echo ""
fi
echo "════════════════════════════════════════════════════════════════"
