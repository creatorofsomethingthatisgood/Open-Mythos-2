// RML — Reinforcement Machine Learning. Go port of engine/rml.py.
//
// Collects user preference signals (explicit /rml good|bad, implicit
// keyword matches, edits, interrupts) and adapts generation params +
// learned system-prompt hints over time. State is persisted to
// $MYTHOS_HOME/rml_preferences.json.
//
// This is the Go-side replacement for the Python RMLEngine used by the
// TUI. The Go CLI exposes it via `mythos rml {stats,good,bad,on,off,reset}`.
package compliance

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// -- signal constants --------------------------------------------------------

const (
	SignalExplicitGood    = 2.0
	SignalExplicitBad     = -2.0
	SignalImplicitPos     = 1.0
	SignalImplicitNeg     = -1.0
	SignalEditPenalty     = -1.0
	SignalInterrupt       = -0.5
)

const maxHistory = 200

var implicitPositiveRe = regexp.MustCompile(`(?i)^(thanks|thank you|perfect|great|exactly|spot on|works|awesome|helpful|that works|that helped|you got it)\s*[!.?]*\s*$`)

var implicitPositiveMidRe = regexp.MustCompile(`(?i)\b(that'?s (right|correct|exactly|it)|spot on|you got it|that works|that helped)\b`)

var implicitNegativeRe = regexp.MustCompile(`(?i)^(no|wrong|bad|incorrect|try again|try differently|not that|not what i (wanted|meant|asked for))\s*[!.?]*\s*$`)

var implicitNegativeMidRe = regexp.MustCompile(`(?i)\b(that'?s (wrong|incorrect|not right|bad)|you'?re (wrong|incorrect)|bad answer|wrong answer|not what i (wanted|meant|asked for)|too (long|verbose|short|vague)|doesn'?t (work|run)|does not (work|run)|wrong code|bad code|insecure|vulnerable|unsafe|incomplete|missing|inaccurate|mistake)\b`)

// negativeCategoryHints maps a keyword phrase to a feedback category.
var negativeCategoryHints = map[string]string{
	"too long":       "conciseness",
	"too verbose":    "conciseness",
	"too short":      "completeness",
	"incomplete":     "completeness",
	"missing":        "completeness",
	"wrong code":     "code_quality",
	"bad code":       "code_quality",
	"doesn't work":   "code_quality",
	"does not work":  "code_quality",
	"doesn't run":    "code_quality",
	"insecure":       "security",
	"vulnerable":     "security",
	"unsafe":         "security",
	"unclear":        "clarity",
	"confusing":      "clarity",
	"inaccurate":     "accuracy",
	"wrong fact":     "accuracy",
	"incorrect":      "accuracy",
	"mistake":        "accuracy",
}

// categoryHintText maps a negative category to a concrete system prompt hint.
var categoryHintText = map[string]string{
	"accuracy":     "Prioritize accuracy over creativity. Double-check facts before stating them. If unsure, say so explicitly.",
	"completeness": "Be thorough and complete. Address all parts of the question. Do not skip steps or leave out edge cases.",
	"clarity":      "Write clearly and structure your response. Use headers, bullet points, and short paragraphs. Avoid jargon without explanation.",
	"code_quality": "Write production-quality code: well-named variables, type hints, docstrings, and error handling. No shortcuts or placeholder comments.",
	"security":     "Apply security best practices: input validation, parameterized queries, no hardcoded secrets, proper error messages (no stack traces to users).",
	"conciseness":  "Be concise. Avoid unnecessary preamble or repetition. Get to the answer quickly; elaborate only when asked.",
}

// -- prefs schema ------------------------------------------------------------

// LearnedHint is a single injected system-prompt hint tied to a category.
type LearnedHint struct {
	Category  string  `json:"category"`
	Hint      string  `json:"hint"`
	Strength  float64 `json:"strength"`
	CreatedAt float64 `json:"created_at"`
	UpdatedAt float64 `json:"updated_at"`
}

// SignalEntry is one recorded feedback signal (kept in history).
type SignalEntry struct {
	Signal   float64 `json:"signal"`
	Source   string  `json:"source"`
	Category string  `json:"category"`
	Detail   string  `json:"detail"`
	TS       float64 `json:"ts"`
}

// ParamAdjustments holds the offsets applied on top of base generation params.
type ParamAdjustments struct {
	TemperatureOffset float64 `json:"temperature_offset"`
	TopPOffset        float64 `json:"top_p_offset"`
	RepeatPenaltyOff  float64 `json:"repeat_penalty_offset"`
}

// Prefs is the persisted RML state.
type Prefs struct {
	Version          int                       `json:"version"`
	Enabled          bool                      `json:"enabled"`
	TotalSignals     int                       `json:"total_signals"`
	CumulativeScore  float64                   `json:"cumulative_score"`
	AcceptCount      int                       `json:"accept_count"`
	RejectCount      int                       `json:"reject_count"`
	SkipCount        int                       `json:"skip_count"`
	EditCount        int                       `json:"edit_count"`
	CategoryScores   map[string]float64        `json:"category_scores"`
	LearnedHints     []LearnedHint             `json:"learned_hints"`
	ParamAdjustments ParamAdjustments           `json:"param_adjustments"`
	History          []SignalEntry             `json:"history"`
	CreatedAt        float64                   `json:"created_at"`
	UpdatedAt        float64                   `json:"updated_at"`
}

func defaultPrefs() *Prefs {
	return &Prefs{
		Version:         1,
		CategoryScores:  map[string]float64{
			"accuracy":     0,
			"completeness": 0,
			"clarity":      0,
			"code_quality": 0,
			"security":     0,
			"conciseness":  0,
		},
		LearnedHints:    []LearnedHint{},
		History:         []SignalEntry{},
	}
}

// RMLPrefsPath returns the path to rml_preferences.json.
func RMLPrefsPath() string {
	return filepath.Join(MythosHome(), "rml_preferences.json")
}

func loadPrefs() *Prefs {
	p := RMLPrefsPath()
	b, err := os.ReadFile(p)
	if err == nil {
		var got Prefs
		if err := json.Unmarshal(b, &got); err == nil {
			// Merge in any new keys from defaults.
			dst := defaultPrefs()
			if got.Version > 0 {
				dst.Version = got.Version
			}
			dst.TotalSignals = got.TotalSignals
			dst.Enabled = got.Enabled
			dst.CumulativeScore = got.CumulativeScore
			dst.AcceptCount = got.AcceptCount
			dst.RejectCount = got.RejectCount
			dst.SkipCount = got.SkipCount
			dst.EditCount = got.EditCount
			if got.CategoryScores == nil {
				dst.CategoryScores = map[string]float64{}
			}
			// Re-apply missing keys from defaults.
			for k, v := range defaultPrefs().CategoryScores {
				if _, ok := got.CategoryScores[k]; !ok {
					dst.CategoryScores[k] = v
				} else {
					dst.CategoryScores[k] = got.CategoryScores[k]
				}
			}
			if got.LearnedHints != nil {
				dst.LearnedHints = got.LearnedHints
			}
			dst.ParamAdjustments = got.ParamAdjustments
			// patch missing adjustments with defaults so divergence stays bounded.
			if got.ParamAdjustments == (ParamAdjustments{}) {
				// keep zeros
			}
			if got.History != nil {
				dst.History = got.History
			}
			dst.CreatedAt = got.CreatedAt
			dst.UpdatedAt = got.UpdatedAt
			return dst
		}
		log.Printf("RML prefs parse failed; starting fresh")
	}
	return defaultPrefs()
}

func savePrefs(p *Prefs) {
	p.UpdatedAt = float64(time.Now().Unix())
	if p.CreatedAt == 0 {
		p.CreatedAt = p.UpdatedAt
	}
	if len(p.History) > maxHistory {
		p.History = p.History[len(p.History)-maxHistory:]
	}
	path := RMLPrefsPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		log.Printf("RML prefs mkdir failed: %v", err)
		return
	}
	b, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		log.Printf("RML prefs marshal failed: %v", err)
		return
	}
	if err := os.WriteFile(path, b, 0o644); err != nil {
		log.Printf("RML prefs save failed: %v", err)
	}
}

// -- RMLEngine --------------------------------------------------------------

// RMLEngine collects preference signals and adapts generation params +
// learned system-prompt hints. Mirrors engine/rml.py's RMLEngine.
type RMLEngine struct {
	Enabled          bool
	LearningRate     float64
	MaxParamOffset   float64
	HintThreshold    float64
	prefs            *Prefs
	sessionSignals   []SignalEntry
}

// NewRMLEngine constructs an RMLEngine from default config (Go CLI path).
func NewRMLEngine() *RMLEngine {
	p := loadPrefs()
	return &RMLEngine{
		prefs:          p,
		Enabled:        p.Enabled,
		LearningRate:   0.05,
		MaxParamOffset: 0.3,
		HintThreshold:  3.0,
	}
}

// Toggle sets (or flips) the enabled state and returns the new state.
// Passing an explicit bool sets the state; nil flips it.
func (r *RMLEngine) Toggle(enabled *bool) bool {
	if enabled != nil {
		r.Enabled = *enabled
	} else {
		r.Enabled = !r.Enabled
	}
	if r.prefs != nil {
		r.prefs.Enabled = r.Enabled
		savePrefs(r.prefs)
	}
	return r.Enabled
}

// RecordSignal records one preference signal and updates prefs/state.
// source is one of "explicit_good","explicit_bad","implicit_pos",
// "implicit_neg","edit","interrupt","manual".
func (r *RMLEngine) RecordSignal(signal float64, source, category, detail string) {
	if !r.Enabled {
		return
	}
	if category == "" {
		category = "accuracy"
	}
	if _, ok := defaultPrefs().CategoryScores[category]; !ok {
		category = "accuracy"
	}
	entry := SignalEntry{
		Signal:   signal,
		Source:   source,
		Category: category,
		Detail:   detail,
		TS:       float64(time.Now().Unix()),
	}
	r.sessionSignals = append(r.sessionSignals, entry)

	r.prefs.TotalSignals++
	r.prefs.CumulativeScore += signal
	if signal > 0 {
		r.prefs.AcceptCount++
	} else if signal < 0 {
		r.prefs.RejectCount++
	}
	if source == "edit" {
		r.prefs.EditCount++
	} else if source == "interrupt" {
		r.prefs.SkipCount++
	}

	// Exponential moving average on category score.
	if old, ok := r.prefs.CategoryScores[category]; ok {
		alpha := r.LearningRate
		if alpha > 0.5 {
			alpha = 0.5
		}
		r.prefs.CategoryScores[category] = old*(1-alpha) + signal*alpha
	}

	r.prefs.History = append(r.prefs.History, entry)
	r.updateParamAdjustments()
	r.updateLearnedHints(category, signal)
	savePrefs(r.prefs)
}

// RecordExplicit records a /rml good|bad signal.
func (r *RMLEngine) RecordExplicit(good bool, category, detail string) {
	if good {
		r.RecordSignal(SignalExplicitGood, "explicit_good", category, detail)
	} else {
		r.RecordSignal(SignalExplicitBad, "explicit_bad", category, detail)
	}
}

// RecordEdit records an output rewrite penalty.
func (r *RMLEngine) RecordEdit(detail string) {
	r.RecordSignal(SignalEditPenalty, "edit", "code_quality", detail)
}

// RecordInterrupt records a generation interrupt penalty.
func (r *RMLEngine) RecordInterrupt() {
	r.RecordSignal(SignalInterrupt, "interrupt", "conciseness", "generation interrupted")
}

// RecordImplicit scans a user follow-up for implicit positive or negative
// signals and records one if found. Returns "positive", "negative", or "".
func (r *RMLEngine) RecordImplicit(text string) string {
	pos := implicitPositiveRe.MatchString(text) || implicitPositiveMidRe.MatchString(text)
	neg := implicitNegativeRe.MatchString(text) || implicitNegativeMidRe.MatchString(text)
	if pos && neg {
		return ""
	}
	if pos {
		cat := r.inferImplicitCategory(text, "accuracy")
		r.RecordSignal(SignalImplicitPos, "implicit_pos", cat, trunc(text, 80))
		return "positive"
	}
	if neg {
		cat := r.inferImplicitCategory(text, "accuracy")
		r.RecordSignal(SignalImplicitNeg, "implicit_neg", cat, trunc(text, 80))
		return "negative"
	}
	return ""
}

func (r *RMLEngine) inferImplicitCategory(text, fallback string) string {
	lower := strings.ToLower(text)
	// Order by phrase length descending so longer phrases win over shorter.
	phrases := make([]string, 0, len(negativeCategoryHints))
	for p := range negativeCategoryHints {
		phrases = append(phrases, p)
	}
	sort.Slice(phrases, func(i, j int) bool { return len(phrases[i]) > len(phrases[j]) })
	for _, p := range phrases {
		if strings.Contains(lower, p) {
			return negativeCategoryHints[p]
		}
	}
	return fallback
}

// -- parameter adaptation ----------------------------------------------------

func (r *RMLEngine) updateParamAdjustments() {
	total := r.prefs.AcceptCount + r.prefs.RejectCount
	if total == 0 {
		return
	}
	acceptRate := float64(r.prefs.AcceptCount) / float64(total)
	editRatio := float64(r.prefs.EditCount)
	if total > 0 {
		editRatio /= float64(total)
	} else {
		editRatio = 0
	}
	lr := r.LearningRate
	cap := r.MaxParamOffset

	// Temperature target: positive = more creative, negative = more precise.
	tempTarget := (acceptRate - 0.5) * 2 * cap
	tempTarget -= editRatio * cap * 0.5

	cur := r.prefs.ParamAdjustments.TemperatureOffset
	new := cur + lr*(tempTarget-cur)
	if new < -cap {
		new = -cap
	}
	if new > cap {
		new = cap
	}
	r.prefs.ParamAdjustments.TemperatureOffset = round4(new)

	// top_p similar but half magnitude.
	tppTarget := tempTarget * 0.5
	curTP := r.prefs.ParamAdjustments.TopPOffset
	newTP := curTP + lr*(tppTarget-curTP)
	if newTP < -cap*0.5 {
		newTP = -cap * 0.5
	}
	if newTP > cap*0.5 {
		newTP = cap * 0.5
	}
	r.prefs.ParamAdjustments.TopPOffset = round4(newTP)

	// repeat_penalty: small nudge based on skip ratio.
	skipRatio := float64(r.prefs.SkipCount)
	if total > 0 {
		skipRatio /= float64(total)
	} else {
		skipRatio = 0
	}
	rpTarget := skipRatio * 0.15
	curRP := r.prefs.ParamAdjustments.RepeatPenaltyOff
	newRP := curRP + lr*(rpTarget-curRP)
	if newRP < -0.2 {
		newRP = -0.2
	}
	if newRP > 0.2 {
		newRP = 0.2
	}
	r.prefs.ParamAdjustments.RepeatPenaltyOff = round4(newRP)
}

// -- learned hints -----------------------------------------------------------

func (r *RMLEngine) updateLearnedHints(category string, signal float64) {
	score, ok := r.prefs.CategoryScores[category]
	if !ok {
		return
	}
	threshold := -r.HintThreshold

	if score > threshold {
		// Category recovered; drop any hints tied to it.
		out := r.prefs.LearnedHints[:0]
		for _, h := range r.prefs.LearnedHints {
			if h.Category != category {
				out = append(out, h)
			}
		}
		r.prefs.LearnedHints = out
		return
	}

	// Update an existing hint for this category.
	for i, h := range r.prefs.LearnedHints {
		if h.Category == category {
			str := absFloat(score)
			if str > 10 {
				str = 10
			}
			r.prefs.LearnedHints[i].Strength = str
			r.prefs.LearnedHints[i].UpdatedAt = float64(time.Now().Unix())
			return
		}
	}

	hintText, ok := categoryHintText[category]
	if !ok {
		return
	}
	str := absFloat(score)
	if str > 10 {
		str = 10
	}
	r.prefs.LearnedHints = append(r.prefs.LearnedHints, LearnedHint{
		Category:  category,
		Hint:      hintText,
		Strength:  str,
		CreatedAt: float64(time.Now().Unix()),
		UpdatedAt: float64(time.Now().Unix()),
	})
}

// LearnedHintsText returns a formatted block of all active learned hints
// for injection into the system prompt. Empty if none.
func (r *RMLEngine) LearnedHintsText() string {
	if len(r.prefs.LearnedHints) == 0 {
		return ""
	}
	hints := make([]LearnedHint, len(r.prefs.LearnedHints))
	copy(hints, r.prefs.LearnedHints)
	sort.SliceStable(hints, func(i, j int) bool { return hints[i].Strength > hints[j].Strength })
	var b strings.Builder
	b.WriteString("\n[RML LEARNED PREFERENCES - adapt your style to match:]\n")
	for _, h := range hints {
		b.WriteString("  - ")
		b.WriteString(h.Hint)
		b.WriteString("\n")
	}
	return b.String()
}

// -- adjusted generation params ---------------------------------------------

// GenConfig is the subset of generation params RML adjusts.
type GenConfig struct {
	Temperature   float64 `json:"temperature"`
	TopP          float64 `json:"top_p"`
	RepeatPenalty float64 `json:"repeat_penalty"`
}

// AdjustedGenerationParams returns a copy of cfg with RML offsets applied.
// If RML is disabled, returns an unmodified copy.
func (r *RMLEngine) AdjustedGenerationParams(cfg GenConfig) GenConfig {
	if !r.Enabled {
		return cfg
	}
	adj := r.prefs.ParamAdjustments
	out := cfg
	out.Temperature = clamp(cfg.Temperature+adj.TemperatureOffset, 0, 2)
	out.TopP = clamp(cfg.TopP+adj.TopPOffset, 0.1, 1.0)
	out.RepeatPenalty = clamp(cfg.RepeatPenalty+adj.RepeatPenaltyOff, 1.0, 1.5)
	return out
}

// -- stats / reset ----------------------------------------------------------

// RMLStats is the RML statistics snapshot for display.
type RMLStats struct {
	Enabled          bool                `json:"enabled"`
	TotalSignals     int                 `json:"total_signals"`
	CumulativeScore  float64             `json:"cumulative_score"`
	AcceptCount      int                 `json:"accept_count"`
	RejectCount      int                 `json:"reject_count"`
	EditCount        int                 `json:"edit_count"`
	SkipCount        int                 `json:"skip_count"`
	AcceptRate       float64             `json:"accept_rate"`
	CategoryScores   map[string]float64  `json:"category_scores"`
	ParamAdjustments ParamAdjustments    `json:"param_adjustments"`
	ActiveHints      int                 `json:"active_hints"`
	SessionSignals   int                 `json:"session_signals"`
}

// Stats returns the current RML statistics snapshot.
func (r *RMLEngine) Stats() RMLStats {
	total := r.prefs.AcceptCount + r.prefs.RejectCount
	acceptRate := 0.0
	if total > 0 {
		acceptRate = float64(r.prefs.AcceptCount) / float64(total) * 100
	}
	return RMLStats{
		Enabled:          r.Enabled,
		TotalSignals:     r.prefs.TotalSignals,
		CumulativeScore:  round2(r.prefs.CumulativeScore),
		AcceptCount:      r.prefs.AcceptCount,
		RejectCount:      r.prefs.RejectCount,
		EditCount:        r.prefs.EditCount,
		SkipCount:        r.prefs.SkipCount,
		AcceptRate:       round1(acceptRate),
		CategoryScores:   r.prefs.CategoryScores,
		ParamAdjustments: r.prefs.ParamAdjustments,
		ActiveHints:      len(r.prefs.LearnedHints),
		SessionSignals:   len(r.sessionSignals),
	}
}

// Reset wipes all learned preferences and starts fresh.
func (r *RMLEngine) Reset() {
	r.prefs = defaultPrefs()
	r.sessionSignals = nil
	savePrefs(r.prefs)
}

// FormatStatsTable renders an ASCII stats table for display.
func (r *RMLEngine) FormatStatsTable() string {
	s := r.Stats()
	var b strings.Builder
	b.WriteString("+==================================================+\n")
	b.WriteString("|           RML - Reinforcement ML Stats           |\n")
	b.WriteString("+==================================================+\n\n")
	enabled := "OFF"
	if s.Enabled {
		enabled = "ON"
	}
	b.WriteString(fmt.Sprintf("  Status:         %s\n", enabled))
	b.WriteString(fmt.Sprintf("  Total signals:  %d\n", s.TotalSignals))
	b.WriteString(fmt.Sprintf("  Score:          %+.2f\n", s.CumulativeScore))
	b.WriteString(fmt.Sprintf("  Accept rate:    %.1f%%\n", s.AcceptRate))
	b.WriteString(fmt.Sprintf("  Accepts:        %d\n", s.AcceptCount))
	b.WriteString(fmt.Sprintf("  Rejects:        %d\n", s.RejectCount))
	b.WriteString(fmt.Sprintf("  Edits:          %d\n", s.EditCount))
	b.WriteString(fmt.Sprintf("  Interrupts:     %d\n", s.SkipCount))
	b.WriteString("\n  Category scores (negative = needs improvement):\n")
	for _, cat := range []string{"accuracy", "completeness", "clarity", "code_quality", "security", "conciseness"} {
		score := s.CategoryScores[cat]
		barLen := int(min(absFloat(score), 5) * 4)
		var bar, marker string
		if score >= 0 {
			bar = strings.Repeat("+", barLen)
			marker = " "
		} else {
			bar = strings.Repeat("-", barLen)
			marker = "!"
		}
		b.WriteString(fmt.Sprintf("    %-16s %+6.2f  %s%s\n", cat, score, marker, bar))
	}
	b.WriteString("\n  Parameter adjustments:\n")
	b.WriteString(fmt.Sprintf("    temperature_offset      %+.4f\n", s.ParamAdjustments.TemperatureOffset))
	b.WriteString(fmt.Sprintf("    top_p_offset            %+.4f\n", s.ParamAdjustments.TopPOffset))
	b.WriteString(fmt.Sprintf("    repeat_penalty_offset   %+.4f\n", s.ParamAdjustments.RepeatPenaltyOff))
	b.WriteString(fmt.Sprintf("    Active hints:           %d\n", s.ActiveHints))
	b.WriteString(fmt.Sprintf("    Session signals:        %d\n\n", s.SessionSignals))
	return b.String()
}

// -- helpers ----------------------------------------------------------------

// RMLCategories returns the valid RML quality categories.
func RMLCategories() []string {
	return []string{"accuracy", "completeness", "clarity", "code_quality", "security", "conciseness"}
}

// IsValidRMLCategory reports whether c is a recognized RML category.
func IsValidRMLCategory(c string) bool {
	for _, cat := range RMLCategories() {
		if cat == c {
			return true
		}
	}
	return false
}

func trunc(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

func round4(f float64) float64 {
	return float64(int64(f*10000+sign(f)*0.5)) / 10000
}

func round2(f float64) float64 {
	return float64(int64(f*100+sign(f)*0.5)) / 100
}

func round1(f float64) float64 {
	return float64(int64(f*10+sign(f)*0.5)) / 10
}

func clamp(f, lo, hi float64) float64 {
	if f < lo {
		return lo
	}
	if f > hi {
		return hi
	}
	return f
}

func absFloat(f float64) float64 {
	if f < 0 {
		return -f
	}
	return f
}

func sign(f float64) float64 {
	if f < 0 {
		return -1
	}
	return 1
}

func min(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}
