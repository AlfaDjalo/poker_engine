#pragma once
// equity_calc.h
// Core equity calculator for CAP poker variants.
// Runs entirely in C++ — zero Python overhead per iteration.
//
// ── REDESIGN (rich equity reporting) ────────────────────────────────
// Previous version tracked fractional win-share per *cell*, where a
// cell was one (point, node_set) pair. That is insufficient to report:
//   - overall scoop / split probability (pot-level, not cell-level)
//   - per-point win / tie probability under "best-of" collapse for
//     points that declare multiple node_sets (matches
//     ShowdownResolver._best_scores_for_point on the Python side)
//   - per-point currency contribution that is consistent with the
//     variant's actual payout_type ("split_pot" vs "points")
//
// This version resolves the FULL pot outcome for every iteration,
// mirroring showdown_resolver.py's resolve() logic (minus side pots,
// which are not meaningful pre-hand), and accumulates both point-level
// and pot-level statistics. See equity_calc.cpp for the algorithm.
// ─────────────────────────────────────────────────────────────────

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
// node_sets: one or more board "views" for this point. Multiple
// node_sets are collapsed "best-of" per player (mirrors
// PointDefinition.node_sets / _best_scores_for_point).
// ─────────────────────────────────────────────────────────────────
struct PointDef {
    std::string name;
    int         score_type;    // mirrors poker_eval::ScoreType enum value
    int         showdown_type; // mirrors poker_eval::ShowdownType enum value

    // True for LOW_A5 / LOW_27 score types: a SMALLER raw score is a
    // BETTER hand, mirroring GameRules.is_low_type() / best_score().
    bool        is_low = false;

    // Low-qualifier threshold (e.g. 8 for 8-or-better), or -1 if this
    // point has no qualifier / is not a low point. Mirrors
    // GameRules.low_qualifier + GameRules.qualifies().
    int         low_qualifier = -1;

    // Name of the paired "high" point to scoop to when nobody
    // qualifies for this (low) point and no_qualify_action == "scoop".
    // Empty string if not set. Mirrors PointDefinition.scoop_from.
    std::string scoop_from;

    std::vector<std::vector<int>> node_sets;
};

// ─────────────────────────────────────────────────────────────────
// Input to the equity calculator
// ─────────────────────────────────────────────────────────────────
struct PlayerInput {
    int              seat;
    std::vector<int> known_cards;
    int              total_hole_cards;
};

struct EquityRequest {
    std::string               variant_name;
    int                       total_hole_cards;
    std::vector<PlayerInput>  players;

    // board_nodes[i] = card id if dealt, -1 if unknown
    std::vector<int>          board_nodes;
    std::vector<PointDef>     points;

    // Payout policy — mirrors GameRules.payout_type / no_qualify_action.
    //   "split_pot" : pot divided evenly across points (best-of collapsed
    //                 per point); each point's slice paid to that
    //                 point's winner(s) independently.
    //   "points"    : each point contributes 1/num_winners to a player's
    //                 tally; whole pot goes to the tally leader(s),
    //                 chopped on ties.
    std::string                payout_type = "points";
    std::string                no_qualify_action = "scoop"; // "scoop" | "eliminate"

    // Evaluation callback — provided by bindings so we reuse poker_eval.
    // IMPORTANT: for LOW-type points, the callback must return 0 for
    // hands that do not meet the point's qualifier — see
    // equity_service.py's evaluator_wrapper. (Qualification is also
    // re-checked in C++ via PointDef::low_qualifier as a safety net.)
    // Signature: evaluate(player_masks, board_mask, score_type, showdown_type)
    //            -> vector<int> of scores (one per player, 0 = no hand)
    std::function<std::vector<int>(
        const std::vector<uint64_t>&, uint64_t, int, int)> evaluator;

    int  exact_threshold = EXACT_THRESHOLD;
    int  mc_iterations   = MC_ITERATIONS;
};

// ─────────────────────────────────────────────────────────────────
// Per-point stats for a single player (fractions 0.0-1.0 unless noted)
// ─────────────────────────────────────────────────────────────────
struct PointStat {
    std::string name;

    // Average fractional share of *this point's* outcome the player
    // receives (e.g. 1.0 if they always win it outright, 0.5 if they
    // always split it two ways, etc). This is the quantity currency
    // contributions are derived from.
    double win_share      = 0.0;

    // P(player is among the winners of this point at all)
    double win_probability = 0.0;

    // P(player wins this point AND it is split with >=1 other player)
    double tie_probability = 0.0;

    // Currency the player expects to receive attributable to this
    // point. For "split_pot" this is exact (pot/num_points * win_share).
    // For "points" payout this is a proportional attribution of the
    // player's overall pot equity across the points they tend to win —
    // see equity_calc.cpp resolve step / equity_service.py post-processing.
    double equity_currency = 0.0;

    // equity_currency / total_pot
    double equity_percent  = 0.0;
};

// ─────────────────────────────────────────────────────────────────
// Overall + per-point equity for one player
// ─────────────────────────────────────────────────────────────────
struct PlayerEquity {
    int    seat = 0;

    // Expected fraction of the WHOLE pot this player receives.
    double overall_equity_fraction = 0.0;

    // overall_equity_fraction * pot_size (0 if pot_size not supplied)
    double overall_equity_currency = 0.0;

    // P(player receives 100% of the pot)
    double scoop_probability = 0.0;

    // P(player receives >0% but <100% of the pot, i.e. any tie/split)
    double split_probability = 0.0;

    std::vector<PointStat> points;
};

// ─────────────────────────────────────────────────────────────────
// Full equity result
// ─────────────────────────────────────────────────────────────────
struct EquityResult {
    std::vector<PlayerEquity> players;
    std::string                method;      // "exact" | "monte_carlo"
    long long                  iterations;
    double                     elapsed_ms;
};

// ─────────────────────────────────────────────────────────────────
// Forward declarations
// pot_size: total chips in the pot. If <= 0, currency fields are left
// at 0.0 and only fraction/probability fields are meaningful (caller
// can multiply by pot size itself if preferred).
// ─────────────────────────────────────────────────────────────────
EquityResult calculate_equity(const EquityRequest& req, double pot_size = 0.0);

} // namespace cap_equity