// equity_calc.cpp
// Core equity engine.  Zero Python overhead — every iteration runs
// entirely in C++ through the evaluator callback provided by the bindings.
//
// ── REDESIGN (rich equity reporting) ────────────────────────────────
// Each iteration now runs the FULL showdown resolution (mirroring
// showdown_resolver.py's resolve(), minus side pots) instead of just
// scoring independent (point, node_set) cells. See header for details
// of the per-iteration algorithm.
//
// ── BUGFIX (exact-enumeration combinatorics) ────────────────────────
// The previous exact-enumeration path treated ALL unknown slots (every
// player's unknown hole cards + every unknown board node) as a single
// undifferentiated combination pool: it picked `n_slots` cards from the
// remaining deck in strictly increasing index order and always assigned
// the i-th smallest chosen card to the i-th slot in a fixed slot order.
//
// That's only correct when slots are genuinely interchangeable — e.g.
// two unknown hole cards belonging to the SAME player (a player's mask
// is a set, so which physical card fills which "slot" doesn't matter),
// or two board nodes that feed the exact same set of (point, node_set)
// pairs (so swapping the cards between them can never change any
// board mask).
//
// It is NOT correct in general. Example: a double-board variant with
// two unseen river nodes, one on each board (node 4 -> board1's point,
// node 9 -> board2's point). These nodes have DIFFERENT signatures —
// swapping which card lands on node 4 vs node 9 changes which board
// gets which card, which is a materially different outcome. The old
// code only ever enumerated the assignment where the numerically
// smaller remaining card went to the earlier node index, silently
// skipping the mirror-image assignments. For 20 remaining cards and 2
// such nodes that reports C(20,2) = 190 combos instead of the correct
// 20*19 = 380 permutations, and the equity numbers derived from it are
// averaged over the wrong (halved, biased) outcome space.
//
// Fix: partition all unknown slots into FUNGIBLE GROUPS before
// enumerating:
//   - all of a given player's unknown hole cards form one group
//     (order-independent — a player's mask is a set).
//   - unknown board nodes are grouped by "signature": the set of
//     (point_index, node_set_index) pairs they belong to. Two nodes
//     are only fungible if their signatures are IDENTICAL (so no
//     point's board mask can ever be affected by which of the two
//     specific nodes gets which specific card).
//
// Each group is then enumerated as its own combination (unordered)
// against the deck as it shrinks, and groups are processed
// sequentially (disjoint draws). This is exactly a multinomial
// enumeration: for the double-board example above, node 4 and node 9
// end up as two SEPARATE size-1 groups, giving 20 * 19 = 380 total
// assignments — matching the true outcome space — while ordinary
// same-board turn/river nodes (identical signature) remain a single
// size-2 group and are still counted as C(n,2), unchanged from before.
//
// Monte Carlo sampling was NOT affected by this bug: it already
// assigns an independent random card to every individual slot
// (including every individual board node), so it was never biased by
// slot fungibility assumptions. Only the exact-enumeration path and
// the combinatorics used to decide exact-vs-Monte-Carlo needed fixing.
// ─────────────────────────────────────────────────────────────────

#include "equity_calc.h"

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <functional>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <unordered_map>

namespace cap_equity {

namespace {
constexpr double EPS = 1e-9;
constexpr long long COMB_CAP = (long long)2e15;
}

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

static inline CardMask card_bit(int card_id) {
    return CardMask(1) << card_id;
}

// C(n, k) — big values are capped at COMB_CAP to avoid overflow
static long long combinations(int n, int k) {
    if (k < 0 || k > n) return 0;
    if (k == 0 || k == n) return 1;
    if (k > n - k) k = n - k;
    long long result = 1;
    for (int i = 0; i < k; ++i) {
        if (result > COMB_CAP / (n - i)) return COMB_CAP; // cap
        result = result * (n - i) / (i + 1);
    }
    return result;
}

// Overflow-safe multiply-with-cap, used to combine per-group
// combination counts into a total exact-enumeration size.
static long long safe_mul_cap(long long a, long long b, long long cap) {
    if (a == 0 || b == 0) return 0;
    if (a > cap / std::max<long long>(b, 1)) return cap;
    return a * b;
}

// ─────────────────────────────────────────────────────────────────
// Slot descriptor — one unknown card position (used for Monte Carlo,
// which is unaffected by the fungibility bug and needs no grouping).
// ─────────────────────────────────────────────────────────────────
enum class SlotKind { PLAYER_HOLE, BOARD_NODE };

struct Slot {
    SlotKind kind;
    int      player_idx;  // for PLAYER_HOLE
    int      node_idx;    // for BOARD_NODE
};

// ─────────────────────────────────────────────────────────────────
// FungibleGroup — one or more unknown slots that are provably
// interchangeable with each other (see file header for the exact
// fungibility rules). Used ONLY by exact enumeration.
// ─────────────────────────────────────────────────────────────────
struct FungibleGroup {
    enum Kind { HOLE, BOARD } kind;
    int              player_idx = -1;   // valid when kind == HOLE
    std::vector<int> node_indices;      // valid when kind == BOARD
    int              count = 0;         // number of cards this group draws
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
// Per-iteration point outcome
// ─────────────────────────────────────────────────────────────────
struct IterationPointResult {
    std::vector<int> winners;   // player indices sharing this point
    bool             voided = false;
};

// ─────────────────────────────────────────────────────────────────
// Accumulator — running totals across all iterations
// ─────────────────────────────────────────────────────────────────
struct Accumulator {
    int n_players;
    int n_points;
    long long count = 0;

    // Pot-level
    std::vector<double>     pot_fraction_sum;   // [player]
    std::vector<long long>  scoop_count;        // [player]
    std::vector<long long>  split_count;        // [player]

    // Point-level
    // point_win_share_sum : accumulated from the RESOLVED winners
    //   (results[pi].winners), i.e. including no-qualify scoop payouts.
    //   Drives currency/equity_percent attribution, which must match
    //   where the pot money actually goes.
    // point_win_count / point_tie_count : accumulated from the DIRECT
    //   qualifiers only (raw_winners[pi]), never via a scoop. Drives
    //   win_probability / tie_probability, which must report a
    //   player's chance of winning THAT point on its own merits — a
    //   no-qualify scoop to another point is zero here.
    std::vector<std::vector<double>>    point_win_share_sum; // [point][player]
    std::vector<std::vector<long long>> point_win_count;     // [point][player]
    std::vector<std::vector<long long>> point_tie_count;     // [point][player]

    Accumulator(int np, int npts)
        : n_players(np), n_points(npts),
          pot_fraction_sum(np, 0.0),
          scoop_count(np, 0),
          split_count(np, 0),
          point_win_share_sum(npts, std::vector<double>(np, 0.0)),
          point_win_count(npts, std::vector<long long>(np, 0)),
          point_tie_count(npts, std::vector<long long>(np, 0)) {}
};

// ─────────────────────────────────────────────────────────────────
// Evaluate one complete runout: full showdown resolution, mirroring
// showdown_resolver.py (minus side pots).
// ─────────────────────────────────────────────────────────────────
static void evaluate_runout(
    const EquityRequest&                        req,
    const RunoutState&                          state,
    const std::unordered_map<std::string, int>& name_to_idx,
    Accumulator&                                acc)
{
    const int n_players = (int)req.players.size();
    const int n_points  = (int)req.points.size();

    // ---- Step 1: collapse each point's node_sets to a best qualifying
    //      score per player (best-of), with a qualifier safety net.
    std::vector<std::vector<int>> best_score(n_points, std::vector<int>(n_players, 0));

    for (int pi = 0; pi < n_points; ++pi) {
        const PointDef& pt = req.points[pi];

        for (const auto& node_set : pt.node_sets) {
            uint64_t board_mask = 0;
            for (int n : node_set) {
                if (n >= 0 && n < (int)state.node_cards.size()) {
                    int c = state.node_cards[n];
                    if (c >= 0) board_mask |= card_bit(c);
                }
            }

            auto scores = req.evaluator(
                state.player_masks, board_mask,
                pt.score_type, pt.showdown_type);

            for (int p = 0; p < n_players && p < (int)scores.size(); ++p) {
                int s = scores[p];
                if (s == 0) continue;

                // Safety net: re-check the low qualifier in case the
                // evaluator callback didn't already zero this out.
                if (pt.is_low && pt.low_qualifier >= 0) {
                    int highest_rank = (s >> 16) & 0xF;
                    if (!(highest_rank > 0 && highest_rank <= pt.low_qualifier)) {
                        continue; // does not qualify
                    }
                }

                int& cur = best_score[pi][p];
                if (cur == 0) {
                    cur = s;
                } else if (pt.is_low ? (s < cur) : (s > cur)) {
                    cur = s;
                }
            }
        }
    }

    // ---- Step 2: raw winners per point (before no-qualify handling)
    std::vector<std::vector<int>> raw_winners(n_points);

    for (int pi = 0; pi < n_points; ++pi) {
        const PointDef& pt = req.points[pi];
        bool have_best = false;
        int  best = 0;

        for (int p = 0; p < n_players; ++p) {
            int s = best_score[pi][p];
            if (s == 0) continue;
            if (!have_best) {
                best = s;
                have_best = true;
            } else if (pt.is_low ? (s < best) : (s > best)) {
                best = s;
            }
        }

        if (!have_best) continue; // no one qualifies

        for (int p = 0; p < n_players; ++p) {
            if (best_score[pi][p] == best) raw_winners[pi].push_back(p);
        }
    }

    // ---- Step 3: apply no-qualify handling (low points only)
    std::vector<IterationPointResult> results(n_points);

    for (int pi = 0; pi < n_points; ++pi) {
        const PointDef& pt = req.points[pi];

        if (!raw_winners[pi].empty()) {
            results[pi].winners = raw_winners[pi];
            continue;
        }

        if (!pt.is_low) {
            results[pi].voided = true; // nobody made any hand at all
            continue;
        }

        if (req.no_qualify_action == "scoop" && !pt.scoop_from.empty()) {
            auto it = name_to_idx.find(pt.scoop_from);
            if (it != name_to_idx.end() && !raw_winners[it->second].empty()) {
                results[pi].winners = raw_winners[it->second];
            } else {
                results[pi].voided = true;
            }
        } else {
            results[pi].voided = true; // "eliminate", or no scoop_from configured
        }
    }

    // ---- Step 4: resolve the pot for this iteration
    std::vector<double> player_pot_fraction(n_players, 0.0);

    if (req.payout_type == "split_pot") {
        if (n_points > 0) {
            double base_share = 1.0 / n_points;
            for (int pi = 0; pi < n_points; ++pi) {
                const auto& winners = results[pi].winners;
                if (winners.empty()) continue; // voided component
                double each = base_share / (double)winners.size();
                for (int p : winners) player_pot_fraction[p] += each;
            }
        }
    } else {
        // "points" payout: tally 1/num_winners per point won
        std::vector<double> tally(n_players, 0.0);
        for (int pi = 0; pi < n_points; ++pi) {
            const auto& winners = results[pi].winners;
            if (winners.empty()) continue;
            double share = 1.0 / (double)winners.size();
            for (int p : winners) tally[p] += share;
        }

        double max_tally = 0.0;
        bool   any = false;
        for (int p = 0; p < n_players; ++p) {
            if (!any || tally[p] > max_tally) { max_tally = tally[p]; any = true; }
        }

        if (any && max_tally > EPS) {
            std::vector<int> pot_winners;
            for (int p = 0; p < n_players; ++p) {
                if (tally[p] >= max_tally - EPS) pot_winners.push_back(p);
            }
            double each = 1.0 / (double)pot_winners.size();
            for (int p : pot_winners) player_pot_fraction[p] += each;
        }
    }

    // ---- Step 5: accumulate
    ++acc.count;

    for (int p = 0; p < n_players; ++p) {
        double frac = player_pot_fraction[p];
        acc.pot_fraction_sum[p] += frac;
        if (frac > 1.0 - EPS) {
            acc.scoop_count[p]++;
        } else if (frac > EPS) {
            acc.split_count[p]++;
        }
    }

    for (int pi = 0; pi < n_points; ++pi) {
        // Currency / win_share attribution follows the RESOLVED winners
        // (results[pi].winners), which include the no-qualify scoop —
        // this must match where the actual pot money goes, mirroring
        // showdown_resolver.py's payout behaviour.
        const auto& payout_winners = results[pi].winners;
        if (!payout_winners.empty()) {
            double payout_share = 1.0 / (double)payout_winners.size();
            for (int p : payout_winners) {
                acc.point_win_share_sum[pi][p] += payout_share;
            }
        }

        // Win / tie PROBABILITY for a point must reflect only players
        // who directly qualified for that point. When nobody qualifies
        // for a low point and it scoops to its paired high point, that
        // is a payout-routing detail, not a "win" of the low point
        // itself — direct (non-scooped) qualifiers get credit here,
        // and everyone else reports zero for this point on this deal.
        const auto& direct_winners = raw_winners[pi];
        if (!direct_winners.empty()) {
            bool tied = direct_winners.size() > 1;
            for (int p : direct_winners) {
                acc.point_win_count[pi][p]++;
                if (tied) acc.point_tie_count[pi][p]++;
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// Build fungible groups for exact enumeration.
//
//   - One HOLE group per player with unknown hole cards (size = count
//     of unknown cards for that player). A player's hand is a set, so
//     any assignment of chosen cards within the group is equivalent.
//
//   - Unknown board nodes are partitioned by "signature": the sorted
//     list of (point_index, node_set_index) pairs the node belongs to.
//     Nodes sharing an identical signature can never produce a
//     different outcome no matter which of them gets which card, so
//     they're grouped together (unordered, like hole cards). Nodes
//     with different signatures — e.g. two different boards' river
//     nodes in a double-board variant — are placed in DIFFERENT
//     groups, which are drawn from the shrinking deck sequentially.
//     That sequential/disjoint draw is what recovers the correct
//     ordered outcome count (20*19 rather than C(20,2) for the
//     double-board example in the file header).
// ─────────────────────────────────────────────────────────────────
static std::vector<FungibleGroup> build_fungible_groups(const EquityRequest& req) {
    std::vector<FungibleGroup> groups;

    // Hole-card groups, one per player with unknown cards.
    for (int pi = 0; pi < (int)req.players.size(); ++pi) {
        int n_unknown = req.players[pi].total_hole_cards
                       - (int)req.players[pi].known_cards.size();
        if (n_unknown > 0) {
            FungibleGroup g;
            g.kind = FungibleGroup::HOLE;
            g.player_idx = pi;
            g.count = n_unknown;
            groups.push_back(std::move(g));
        }
    }

    // Board-node groups, partitioned by (point, node_set) signature.
    std::vector<int> unknown_nodes;
    for (int ni = 0; ni < (int)req.board_nodes.size(); ++ni) {
        if (req.board_nodes[ni] < 0) unknown_nodes.push_back(ni);
    }

    auto signature_of = [&](int node) {
        std::vector<std::pair<int, int>> sig;
        for (int pi = 0; pi < (int)req.points.size(); ++pi) {
            const auto& node_sets = req.points[pi].node_sets;
            for (int nsi = 0; nsi < (int)node_sets.size(); ++nsi) {
                for (int n : node_sets[nsi]) {
                    if (n == node) { sig.push_back({pi, nsi}); break; }
                }
            }
        }
        return sig;
    };

    std::vector<std::vector<std::pair<int, int>>> sigs(unknown_nodes.size());
    for (size_t i = 0; i < unknown_nodes.size(); ++i) {
        sigs[i] = signature_of(unknown_nodes[i]);
    }

    std::vector<bool> grouped(unknown_nodes.size(), false);
    for (size_t i = 0; i < unknown_nodes.size(); ++i) {
        if (grouped[i]) continue;
        FungibleGroup g;
        g.kind = FungibleGroup::BOARD;
        g.node_indices.push_back(unknown_nodes[i]);
        grouped[i] = true;
        for (size_t j = i + 1; j < unknown_nodes.size(); ++j) {
            if (!grouped[j] && sigs[j] == sigs[i]) {
                g.node_indices.push_back(unknown_nodes[j]);
                grouped[j] = true;
            }
        }
        g.count = (int)g.node_indices.size();
        groups.push_back(std::move(g));
    }

    return groups;
}

// Total number of exact outcomes for a set of fungible groups drawing
// sequentially (without replacement) from a deck of n_remain cards.
// This is a multinomial coefficient: n! / (k1! k2! ... (n-K)!), which
// is independent of the order groups are processed in.
static long long total_exact_combos(int n_remain, const std::vector<FungibleGroup>& groups) {
    long long combos = 1;
    int n_avail = n_remain;
    for (const auto& g : groups) {
        long long c = combinations(n_avail, g.count);
        combos = safe_mul_cap(combos, c, COMB_CAP);
        n_avail -= g.count;
    }
    return combos;
}

// ─────────────────────────────────────────────────────────────────
// Exact enumeration over fungible groups.
//
// For each group, choose a combination (unordered — see
// build_fungible_groups for why this is valid) of `count` cards from
// the currently-available pool, assign them to the group's target(s)
// in a fixed order (harmless: within a group any assignment order is
// equivalent), recurse into the next group with those cards removed
// from the pool, then undo before trying the next combination.
// ─────────────────────────────────────────────────────────────────
static void enumerate_groups(
    const EquityRequest&                        req,
    const std::vector<int>&                     available,
    const std::vector<FungibleGroup>&            groups,
    int                                          group_idx,
    RunoutState&                                 state,
    const std::unordered_map<std::string, int>& name_to_idx,
    Accumulator&                                acc)
{
    if (group_idx == (int)groups.size()) {
        evaluate_runout(req, state, name_to_idx, acc);
        return;
    }

    const FungibleGroup& g = groups[group_idx];
    const int k = g.count;
    const int n = (int)available.size();

    if (k == 0) {
        enumerate_groups(req, available, groups, group_idx + 1, state, name_to_idx, acc);
        return;
    }

    std::vector<int> combo(k);

    std::function<void(int, int)> rec = [&](int start, int depth) {
        if (depth == k) {
            // Build the next available pool (available minus the chosen combo).
            std::vector<bool> used(n, false);
            for (int idx : combo) used[idx] = true;
            std::vector<int> next_available;
            next_available.reserve(n - k);
            for (int i = 0; i < n; ++i) {
                if (!used[i]) next_available.push_back(available[i]);
            }

            // Apply this combo's assignment.
            for (int d = 0; d < k; ++d) {
                int card = available[combo[d]];
                if (g.kind == FungibleGroup::HOLE) {
                    state.player_masks[g.player_idx] |= card_bit(card);
                } else {
                    state.node_cards[g.node_indices[d]] = card;
                }
            }

            enumerate_groups(req, next_available, groups, group_idx + 1, state, name_to_idx, acc);

            // Undo.
            for (int d = 0; d < k; ++d) {
                int card = available[combo[d]];
                if (g.kind == FungibleGroup::HOLE) {
                    state.player_masks[g.player_idx] &= ~card_bit(card);
                } else {
                    state.node_cards[g.node_indices[d]] = -1;
                }
            }
            return;
        }
        for (int i = start; i < n; ++i) {
            combo[depth] = i;
            rec(i + 1, depth + 1);
        }
    };

    rec(0, 0);
}

// ─────────────────────────────────────────────────────────────────
// Monte Carlo sampling
//
// Unaffected by the fungibility bug: every individual slot (including
// every individual board node) independently receives a distinct
// random card each iteration, so board-node "signature" never enters
// into it — the sampling is already correct for double-board and any
// other layout.
// ─────────────────────────────────────────────────────────────────
static void monte_carlo(
    const EquityRequest&                        req,
    const std::vector<int>&                     remaining_deck,
    const std::vector<Slot>&                     slots,
    int                                          iterations,
    RunoutState&                                 state,
    const std::unordered_map<std::string, int>& name_to_idx,
    Accumulator&                                acc)
{
    std::mt19937 rng(std::random_device{}());
    std::vector<int> deck_copy = remaining_deck;

    for (int iter = 0; iter < iterations; ++iter) {
        int n_slots = (int)slots.size();
        for (int i = 0; i < n_slots; ++i) {
            int j = i + (int)(rng() % (deck_copy.size() - i));
            std::swap(deck_copy[i], deck_copy[j]);
        }

        for (int s = 0; s < n_slots; ++s) {
            int card = deck_copy[s];
            const Slot& slot = slots[s];
            if (slot.kind == SlotKind::PLAYER_HOLE) {
                state.player_masks[slot.player_idx] |= card_bit(card);
            } else {
                state.node_cards[slot.node_idx] = card;
            }
        }

        evaluate_runout(req, state, name_to_idx, acc);

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
EquityResult calculate_equity(const EquityRequest& req, double pot_size) {
    using Clock = std::chrono::high_resolution_clock;
    auto t_start = Clock::now();

    if (!req.evaluator)
        throw std::invalid_argument("EquityRequest::evaluator must be set");
    if (req.players.empty())
        throw std::invalid_argument("At least one player is required");
    if (req.points.empty())
        throw std::invalid_argument("At least one scoring point is required");

    int n_players = (int)req.players.size();
    int n_points  = (int)req.points.size();

    // name -> index, for scoop_from lookups
    std::unordered_map<std::string, int> name_to_idx;
    for (int i = 0; i < n_points; ++i) name_to_idx[req.points[i].name] = i;

    // ── Build dead card mask ──────────────────────────────────────
    CardMask dead = 0;

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

    // ── Build Slot list (Monte Carlo path only) ─────────────────────
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

    // ── Build fungible groups (exact-enumeration path only) ────────
    std::vector<FungibleGroup> groups = build_fungible_groups(req);

    Accumulator acc(n_players, n_points);

    // ── Choose strategy ───────────────────────────────────────────
    int n_slots  = (int)slots.size();
    int n_remain = (int)remaining_deck.size();
    long long combs = total_exact_combos(n_remain, groups);

    std::string method;
    if (n_slots == 0) {
        method = "exact";
        evaluate_runout(req, state, name_to_idx, acc);
    } else if (combs <= (long long)req.exact_threshold) {
        method = "exact";
        enumerate_groups(req, remaining_deck, groups, 0, state, name_to_idx, acc);
    } else {
        method = "monte_carlo";
        monte_carlo(req, remaining_deck, slots,
                    req.mc_iterations, state, name_to_idx, acc);
    }

    // ── Normalise into EquityResult ─────────────────────────────────
    EquityResult result;
    result.method     = method;
    result.iterations = acc.count;

    double inv = (acc.count > 0) ? (1.0 / (double)acc.count) : 0.0;

    result.players.resize(n_players);
    for (int p = 0; p < n_players; ++p) {
        PlayerEquity& pe = result.players[p];
        pe.seat = req.players[p].seat;
        pe.overall_equity_fraction = acc.pot_fraction_sum[p] * inv;
        pe.overall_equity_currency = pe.overall_equity_fraction * pot_size;
        pe.scoop_probability = (double)acc.scoop_count[p] * inv;
        pe.split_probability = (double)acc.split_count[p] * inv;

        // Sum of per-point win-shares, used to proportionally attribute
        // overall equity currency across points for "points" payout type
        // (split_pot has an exact formula and doesn't need this).
        double win_share_total = 0.0;
        std::vector<double> win_share(n_points, 0.0);
        for (int pi = 0; pi < n_points; ++pi) {
            win_share[pi] = acc.point_win_share_sum[pi][p] * inv;
            win_share_total += win_share[pi];
        }

        pe.points.resize(n_points);
        for (int pi = 0; pi < n_points; ++pi) {
            PointStat& ps = pe.points[pi];
            ps.name           = req.points[pi].name;
            ps.win_share       = win_share[pi];
            ps.win_probability = (double)(acc.point_win_count[pi][p] - acc.point_tie_count[pi][p]) * inv;
            ps.tie_probability = (double)acc.point_tie_count[pi][p] * inv;

            if (req.payout_type == "split_pot") {
                double component_frac = (n_points > 0) ? (1.0 / n_points) : 0.0;
                ps.equity_currency = pot_size * component_frac * ps.win_share;
            } else {
                ps.equity_currency = (win_share_total > EPS)
                    ? pe.overall_equity_currency * (win_share[pi] / win_share_total)
                    : 0.0;
            }
            ps.equity_percent = (pot_size > 0.0) ? (ps.equity_currency / pot_size) : 0.0;
        }
    }

    auto t_end = Clock::now();
    result.elapsed_ms =
        std::chrono::duration<double, std::milli>(t_end - t_start).count();

    return result;
}

} // namespace cap_equity