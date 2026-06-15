#pragma once
// equity_calc.h
// Core equity calculator for CAP poker variants.
// Runs entirely in C++ — zero Python overhead per iteration.
//
// Architecture:
//   EquityRequest  — input description (players, board nodes, points to evaluate)
//   EquityResult   — per-player, per-point equity fractions
//   EquityCalc     — the calculator (enumerate or Monte Carlo)
//
// The caller (Python bindings or unit tests) is responsible for:
//   - building EquityRequest from game state
//   - calling EquityCalc::calculate()
//   - interpreting EquityResult

#include <array>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace cap_equity {

// ─────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────

static constexpr int DECK_SIZE       = 52;
static constexpr int MAX_PLAYERS     = 9;
static constexpr int MAX_NODES       = 20;
static constexpr int MAX_POINTS      = 16;
static constexpr int EXACT_THRESHOLD = 50000;   // switch to MC above this
static constexpr int MC_ITERATIONS   = 20000;

using CardMask = uint64_t;

// ─────────────────────────────────────────────────────────────────
// A single scoring point definition
// node_indices: which board nodes contribute to this point's board mask
// ─────────────────────────────────────────────────────────────────
struct PointDef {
    std::string name;
    int         score_type;   // mirrors poker_eval::ScoreType enum value
    int         showdown_type; // mirrors poker_eval::ShowdownType enum value
    // Each inner vector is one "board" (node_set) for this point.
    // Most points have one board; split-board games have several.
    std::vector<std::vector<int>> node_sets;
};

// ─────────────────────────────────────────────────────────────────
// Input to the equity calculator
// ─────────────────────────────────────────────────────────────────
struct PlayerInput {
    int              seat;
    // Known hole cards (card ids 0-51). Size may be less than the
    // game's hole_cards count — unknowns are filled during runout.
    std::vector<int> known_cards;
    int              total_hole_cards; // how many the game deals (e.g. 2, 4, 6)
};

struct EquityRequest {
    std::string               variant_name;
    int                       total_hole_cards; // per player
    std::vector<PlayerInput>  players;
    // board_nodes[i] = card id if dealt, -1 if unknown
    std::vector<int>          board_nodes;
    std::vector<PointDef>     points;
    // Evaluation callback — provided by bindings so we reuse poker_eval
    // Signature: evaluate(player_masks, board_mask, score_type, showdown_type)
    //            -> vector<int> of scores (one per player, 0 = no hand)
    std::function<std::vector<int>(
        const std::vector<uint64_t>&, uint64_t, int, int)> evaluator;

    int  exact_threshold = EXACT_THRESHOLD;
    int  mc_iterations   = MC_ITERATIONS;
};

// ─────────────────────────────────────────────────────────────────
// Per-point equity for each player  (fractions 0.0–1.0)
// ─────────────────────────────────────────────────────────────────
struct EquityResult {
    // equity[player_index][point_name] = fraction
    std::vector<std::vector<double>>     equity;   // [player][point_board]
    std::vector<std::string>             point_names;
    std::string                          method;   // "exact" | "monte_carlo"
    long long                            iterations;
    double                               elapsed_ms;
};

// ─────────────────────────────────────────────────────────────────
// Forward declarations
// ─────────────────────────────────────────────────────────────────
EquityResult calculate_equity(const EquityRequest& req);

} // namespace cap_equity