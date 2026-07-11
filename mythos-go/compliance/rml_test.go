package compliance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// withRMLTempHome sets MYTHOS_HOME so RML preferences cannot leak into
// the user's real ~/.config/mythos/.
func withRMLTempHome(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("MYTHOS_HOME", dir)
	return dir
}

func TestRMLStartsDisabled(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	if r.Enabled {
		t.Fatal("RML must start disabled")
	}
}

func TestRMLToggle(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	if !r.Toggle(&on) {
		t.Fatal("Toggle(true) returned false")
	}
	if !r.Enabled {
		t.Fatal("Toggle(true) did not set Enabled")
	}
	off := false
	if r.Toggle(&off) {
		t.Fatal("Toggle(false) returned true")
	}
	if r.Enabled {
		t.Fatal("Toggle(false) did not clear Enabled")
	}
	// nil flips.
	if !r.Toggle(nil) {
		t.Fatal("Toggle(nil) should flip to true from false")
	}
}

func TestRMLDisabledRejectsSignals(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	r.RecordSignal(SignalExplicitGood, "explicit_good", "accuracy", "test")
	s := r.Stats()
	if s.TotalSignals != 0 {
		t.Fatalf("disabled engine recorded a signal: %d", s.TotalSignals)
	}
}

func TestRMLExplicitGoodAndBad(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	r.RecordExplicit(true, "accuracy", "")
	r.RecordExplicit(false, "completeness", "")
	s := r.Stats()
	if s.TotalSignals != 2 {
		t.Fatalf("TotalSignals=%d want 2", s.TotalSignals)
	}
	if s.AcceptCount != 1 || s.RejectCount != 1 {
		t.Fatalf("accept=%d reject=%d want 1/1", s.AcceptCount, s.RejectCount)
	}
	if s.CumulativeScore != 0.0 {
		t.Fatalf("CumulativeScore=%v want 0 (+2 + -2)", s.CumulativeScore)
	}
	// accuracy should be positive; completeness negative.
	acc := r.prefs.CategoryScores["accuracy"]
	cmp := r.prefs.CategoryScores["completeness"]
	if acc <= 0 {
		t.Fatalf("accuracy score %v should be positive", acc)
	}
	if cmp >= 0 {
		t.Fatalf("completeness score %v should be negative", cmp)
	}
}

func TestRMLRecordEditAndInterrupt(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	r.RecordEdit("user rewrote code")
	r.RecordInterrupt()
	s := r.Stats()
	if s.EditCount != 1 {
		t.Fatalf("EditCount=%d want 1", s.EditCount)
	}
	if s.SkipCount != 1 {
		t.Fatalf("SkipCount=%d want 1", s.SkipCount)
	}
}

func TestRMLImplicitPositive(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	got := r.RecordImplicit("thanks!")
	if got != "positive" {
		t.Fatalf("RecordImplicit(thanks!)=%q want positive", got)
	}
	got = r.RecordImplicit("that's correct")
	if got != "positive" {
		t.Fatalf("RecordImplicit(that's correct)=%q want positive", got)
	}
}

func TestRMLImplicitNegative(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	got := r.RecordImplicit("wrong.")
	if got != "negative" {
		t.Fatalf("RecordImplicit(wrong.)=%q want negative", got)
	}
	got = r.RecordImplicit("that's not right")
	if got != "negative" {
		t.Fatalf("RecordImplicit(that's not right)=%q want negative", got)
	}
	got = r.RecordImplicit("hi there")
	if got != "" {
		t.Fatalf("RecordImplicit(neutral)=%q want empty", got)
	}
}

func TestRMLImplicitCategoryInference(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	r.RecordImplicit("this is too long")
	if r.prefs.CategoryScores["conciseness"] >= 0 {
		t.Fatalf("too-long should decrement conciseness, got %v", r.prefs.CategoryScores["conciseness"])
	}
	r2 := NewRMLEngine()
	r2.Toggle(&on)
	r2.RecordImplicit("your code is wrong and doesn't work")
	if r2.prefs.CategoryScores["code_quality"] >= 0 {
		t.Fatalf("doesn't-work should decrement code_quality, got %v", r2.prefs.CategoryScores["code_quality"])
	}
}

func TestRMLPersistenceAcrossEngines(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	for i := 0; i < 4; i++ {
		r.RecordExplicit(false, "conciseness", "")
	}
	// File written.
	p := RMLPrefsPath()
	if _, err := os.Stat(p); err != nil {
		t.Fatalf("prefs not written: %v", err)
	}
	// Fresh engine loads it.
	r2 := NewRMLEngine()
	if r2.prefs.TotalSignals != r.prefs.TotalSignals {
		t.Fatalf("TotalSignals did not round-trip: %d vs %d", r2.prefs.TotalSignals, r.prefs.TotalSignals)
	}
	if r2.prefs.RejectCount != 4 {
		t.Fatalf("RejectCount=%d want 4", r2.prefs.RejectCount)
	}
	if r2.prefs.CategoryScores["conciseness"] >= 0 {
		t.Fatalf("conciseness score should be negative after 4 bad, got %v", r2.prefs.CategoryScores["conciseness"])
	}
}

func TestRMLLearnedHintAtThreshold(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	r.LearningRate = 0.5
	r.HintThreshold = 1.0
	on := true
	r.Toggle(&on)
	// Hammer conciseness with bad signals until a hint appears.
	for i := 0; i < 20; i++ {
		r.RecordExplicit(false, "conciseness", "")
	}
	text := r.LearnedHintsText()
	if text == "" {
		t.Fatal("expected a learned hint after sustained negative signal")
	}
	if !strings.Contains(text, "RML LEARNED PREFERENCES") {
		t.Fatalf("learned-hints block missing header: %q", text)
	}
	if !strings.Contains(text, "concise") {
		t.Fatalf("learned-hints block missing conciseness guidance: %q", text)
	}
}

func TestRMLResetClearsState(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	r.RecordExplicit(true, "accuracy", "")
	r.RecordExplicit(false, "completeness", "")
	r.Reset()
	s := r.Stats()
	if s.TotalSignals != 0 || s.AcceptCount != 0 || s.RejectCount != 0 {
		t.Fatalf("reset failed: %+v", s)
	}
	if r.LearnedHintsText() != "" {
		t.Fatal("reset left a learned hint")
	}
}

func TestRMLAdjustedGenerationParamsDisabled(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	base := GenConfig{Temperature: 0.7, TopP: 0.9, RepeatPenalty: 1.1}
	out := r.AdjustedGenerationParams(base)
	// RML disabled -> no adjustment.
	if out.Temperature != 0.7 || out.TopP != 0.9 || out.RepeatPenalty != 1.1 {
		t.Fatalf("disabled RML should not change params: %+v", out)
	}
}

func TestRMLStatsTableRenders(t *testing.T) {
	withRMLTempHome(t)
	r := NewRMLEngine()
	on := true
	r.Toggle(&on)
	r.RecordExplicit(true, "accuracy", "")
	out := r.FormatStatsTable()
	for _, want := range []string{"RML", "Status:", "ON", "Total signals:", "Category scores"} {
		if !strings.Contains(out, want) {
			t.Fatalf("stats table missing %q in:\n%s", want, out)
		}
	}
}

func TestRMLPrefsPathEnv(t *testing.T) {
	t.Setenv("MYTHOS_HOME", "/tmp/fake-rml-home")
	if got := RMLPrefsPath(); got != filepath.Join("/tmp/fake-rml-home", "rml_preferences.json") {
		t.Fatalf("RMLPrefsPath = %q, want /tmp/fake-rml-home/rml_preferences.json", got)
	}
}

func TestIsValidRMLCategory(t *testing.T) {
	for _, c := range RMLCategories() {
		if !IsValidRMLCategory(c) {
			t.Errorf("category %q should be valid", c)
		}
	}
	if IsValidRMLCategory("bogus") {
		t.Error("bogus category should be invalid")
	}
}
