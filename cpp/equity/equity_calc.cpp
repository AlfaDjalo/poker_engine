// equity_calc.cpp
// Core equity engine.  Zero Python overhead — every iteration runs
// entirely in C++ through the evaluator callback provided by the bindings.
//
// Strategy:
//   1. Build the "dead card" mask from all known cards.
//   2. Build an ordered list of "unknown slots":
//        - per-player unknown hole card slots (total_hole_cards - known_cards.size())
//        - per-node unknown board slots (board_nodes[i] == -1)
//   3. Count remaining deck cards (DECK_SIZE - |dead|).
//   4. Choose exact or Monte Carlo based on C(remaining, unknowns).
//   5. For each complete runout:
//        a. For each PointDef x node_set, compute board_mask from assigned nodes.
//        b. Call evaluator(player_masks, board_mask, score_type, showdown_type).
//        c. Find the max score(s); add fractional win to tallies.
//   6. Normalise tallies by total iterations and return.

#include "equity_calc.h"

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <numeric>
#include <random>
#include <stdexcept>

namespace cap_equity {

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

static inline CardMask card_bit(int card_id) {
    return CardMask(1) << card_id;
}

// C(n, k) — big values are capped at LLONG_MAX to avoid overflow
static long long combinations(int n, int k) {
    if (k < 0 || k > n) return 0;
    if (k == 0 || k == n) return 1;
    if (k > n - k) k = n - k;
    long long result = 1;
    for (int i = 0; i < k; ++i) {
        if (result > (long long)2e15 / (n - i)) return (long long)2e15; // cap
        result = result * (n - i) / (i + 1);
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────
// Slot descriptor — one unknown card position
// ─────────────────────────────────────────────────────────────────
enum class SlotKind { PLAYER_HOLE, BOARD_NODE };

struct Slot {
    SlotKind kind;
    int      player_idx;  // for PLAYER_HOLE
    int      node_idx;    // for BOARD_NODE
};

// ─────────────────────────────────────────────────────────────────
// RunoutState — mutable state passed through the enumeration
// ─────────────────────────────────────────────────────────────────
struct RunoutState {
    // player_masks[i] = bitmask of hole cards for player i (includes known + drawn)
    std::vector<uint64_t> player_masks;
    // node_cards[i] = card id of node i (-1 if unknown and not yet drawn)
    std::vector<int>      node_cards;
};

// ─────────────────────────────────────────────────────────────────
// Accumulator — tracks fractional wins per player per point-board
// ─────────────────────────────────────────────────────────────────
// Indexed as [point_board_flat][player_idx]
// point_board_flat = sum of all board counts for previous points + board_idx

struct Accumulator {
    int                               n_players;
    int                               n_cells;   // total point-boards
    std::vector<std::vector<double>>  wins;       // [cell][player]
    long long                         count = 0;

    Accumulator(int np, int nc)
        : n_players(np), n_cells(nc),
          wins(nc, std::vector<double>(np, 0.0)) {}

    void record(int cell, const std::vector<int>& scores) {
        // Find the best score among active players (score 0 = no hand / folded)
        int best = 0;
        for (int s : scores) best = std::max(best, s);
        if (best == 0) return; // no one qualifies

        // Count winners
        int n_winners = 0;
        for (int s : scores) if (s == best) ++n_winners;

        double share = 1.0 / n_winners;
        for (int p = 0; p < n_players; ++p) {
            if (scores[p] == best) wins[cell][p] += share;
        }
    }
};

// ─────────────────────────────────────────────────────────────────
// Evaluate one complete runout and record into accumulator
// ─────────────────────────────────────────────────────────────────
static void evaluate_runout(
    const EquityRequest& req,
    const RunoutState&   state,
    Accumulator&         acc)
{
    int cell = 0;
    for (const auto& pt : req.points) {
        for (const auto& node_set : pt.node_sets) {
            // Build board mask for this node_set
            uint64_t board_mask = 0;
            for (int n : node_set) {
                if (n >= 0 && n < (int)state.node_cards.size()) {
                    int c = state.node_cards[n];
                    if (c >= 0) board_mask |= card_bit(c);
                }
            }

            // Call the evaluator (Python callback)
            auto scores = req.evaluator(
                state.player_masks, board_mask,
                pt.score_type, pt.showdown_type);

            acc.record(cell, scores);
            ++cell;
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// Exact enumeration — recursive combination generation
// ─────────────────────────────────────────────────────────────────
static void enumerate_recursive(
    const EquityRequest&       req,
    const std::vector<int>&    remaining_deck,  // sorted available cards
    const std::vector<Slot>&   slots,
    int                        slot_idx,
    int                        deck_start,      // next card to consider
    RunoutState&               state,
    Accumulator&               acc)
{
    if (slot_idx == (int)slots.size()) {
        ++acc.count;
        evaluate_runout(req, state, acc);
        return;
    }

    const Slot& slot = slots[slot_idx];

    for (int di = deck_start; di < (int)remaining_deck.size(); ++di) {
        int card = remaining_deck[di];

        // Assign card to this slot
        if (slot.kind == SlotKind::PLAYER_HOLE) {
            state.player_masks[slot.player_idx] |= card_bit(card);
        } else {
            state.node_cards[slot.node_idx] = card;
        }

        enumerate_recursive(req, remaining_deck, slots,
                            slot_idx + 1, di + 1, state, acc);

        // Unassign
        if (slot.kind == SlotKind::PLAYER_HOLE) {
            state.player_masks[slot.player_idx] &= ~card_bit(card);
        } else {
            state.node_cards[slot.node_idx] = -1;
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// Monte Carlo sampling
// ─────────────────────────────────────────────────────────────────
static void monte_carlo(
    const EquityRequest&     req,
    const std::vector<int>&  remaining_deck,
    const std::vector<Slot>& slots,
    int                      iterations,
    RunoutState&             state,
    Accumulator&             acc)
{
    std::mt19937 rng(std::random_device{}());
    std::vector<int> deck_copy = remaining_deck;

    for (int iter = 0; iter < iterations; ++iter) {
        // Partial Fisher-Yates shuffle — only shuffle as many cards as we need
        int n_slots = (int)slots.size();
        for (int i = 0; i < n_slots; ++i) {
            int j = i + (int)(rng() % (deck_copy.size() - i));
            std::swap(deck_copy[i], deck_copy[j]);
        }

        // Assign shuffled cards to slots
        for (int s = 0; s < n_slots; ++s) {
            int card = deck_copy[s];
            const Slot& slot = slots[s];
            if (slot.kind == SlotKind::PLAYER_HOLE) {
                state.player_masks[slot.player_idx] |= card_bit(card);
            } else {
                state.node_cards[slot.node_idx] = card;
            }
        }

        ++acc.count;
        evaluate_runout(req, state, acc);

        // Unassign
        for (int s = 0; s < n_slots; ++s) {
            const Slot& slot = slots[s];
            if (slot.kind == SlotKind::PLAYER_HOLE) {
                state.player_masks[slot.player_idx] &= ~card_bit(deck_copy[s]);
            } else {
                state.node_cards[slot.node_idx] = -1;
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// Public entry point
// ─────────────────────────────────────────────────────────────────
EquityResult calculate_equity(const EquityRequest& req) {
    using Clock = std::chrono::high_resolution_clock;
    auto t_start = Clock::now();

    if (!req.evaluator)
        throw std::invalid_argument("EquityRequest::evaluator must be set");
    if (req.players.empty())
        throw std::invalid_argument("At least one player is required");
    if (req.points.empty())
        throw std::invalid_argument("At least one scoring point is required");

    int n_players = (int)req.players.size();

    // ── Build dead card mask ──────────────────────────────────────
    CardMask dead = 0;

    // Initialise RunoutState with known cards
    RunoutState state;
    state.player_masks.resize(n_players, 0);
    state.node_cards = req.board_nodes; // -1 for unknowns

    for (int pi = 0; pi < n_players; ++pi) {
        for (int c : req.players[pi].known_cards) {
            if (c < 0 || c >= DECK_SIZE)
                throw std::invalid_argument("Invalid card id: " + std::to_string(c));
            if (dead & card_bit(c))
                throw std::invalid_argument("Duplicate card id: " + std::to_string(c));
            dead |= card_bit(c);
            state.player_masks[pi] |= card_bit(c);
        }
    }
    for (int c : req.board_nodes) {
        if (c < 0) continue;
        if (c >= DECK_SIZE)
            throw std::invalid_argument("Invalid board card id: " + std::to_string(c));
        if (dead & card_bit(c))
            throw std::invalid_argument("Duplicate board card id: " + std::to_string(c));
        dead |= card_bit(c);
    }

    // ── Build remaining deck ──────────────────────────────────────
    std::vector<int> remaining_deck;
    remaining_deck.reserve(DECK_SIZE);
    for (int c = 0; c < DECK_SIZE; ++c) {
        if (!(dead & card_bit(c))) remaining_deck.push_back(c);
    }

    // ── Build slot list ───────────────────────────────────────────
    std::vector<Slot> slots;

    for (int pi = 0; pi < n_players; ++pi) {
        int n_unknown = req.players[pi].total_hole_cards
                      - (int)req.players[pi].known_cards.size();
        for (int j = 0; j < n_unknown; ++j) {
            slots.push_back({SlotKind::PLAYER_HOLE, pi, -1});
        }
    }
    for (int ni = 0; ni < (int)req.board_nodes.size(); ++ni) {
        if (req.board_nodes[ni] < 0) {
            slots.push_back({SlotKind::BOARD_NODE, -1, ni});
        }
    }

    // ── Count total point-board cells for the accumulator ────────
    int n_cells = 0;
    std::vector<std::string> cell_names;
    for (const auto& pt : req.points) {
        for (int b = 0; b < (int)pt.node_sets.size(); ++b) {
            n_cells++;
            if (pt.node_sets.size() == 1) {
                cell_names.push_back(pt.name);
            } else {
                cell_names.push_back(pt.name + "_board" + std::to_string(b + 1));
            }
        }
    }

    Accumulator acc(n_players, n_cells);

    // ── Choose strategy ───────────────────────────────────────────
    int n_slots    = (int)slots.size();
    int n_remain   = (int)remaining_deck.size();
    long long combs = combinations(n_remain, n_slots);

    std::string method;
    if (n_slots == 0) {
        // All cards known — single evaluation
        method = "exact";
        ++acc.count;
        evaluate_runout(req, state, acc);
    } else if (combs <= (long long)req.exact_threshold) {
        method = "exact";
        enumerate_recursive(req, remaining_deck, slots,
                            0, 0, state, acc);
    } else {
        method = "monte_carlo";
        monte_carlo(req, remaining_deck, slots,
                    req.mc_iterations, state, acc);
    }

    // ── Normalise ─────────────────────────────────────────────────
    EquityResult result;
    result.method      = method;
    result.iterations  = acc.count;
    result.point_names = cell_names;

    result.equity.resize(n_players, std::vector<double>(n_cells, 0.0));
    if (acc.count > 0) {
        double inv = 1.0 / (double)acc.count;
        for (int pi = 0; pi < n_players; ++pi) {
            for (int ci = 0; ci < n_cells; ++ci) {
                result.equity[pi][ci] = acc.wins[ci][pi] * inv;
            }
        }
    }

    auto t_end   = Clock::now();
    result.elapsed_ms =
        std::chrono::duration<double, std::milli>(t_end - t_start).count();

    return result;
}

} // namespace cap_equity