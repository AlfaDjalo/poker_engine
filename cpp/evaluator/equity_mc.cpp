// evaluator/equity_mc.cpp
//
// Heads-up Texas Hold'em matchup counts for RL training: given two
// 2-card hole masks and a (possibly partial) board mask, return how many
// board runouts A wins / ties / B wins.
//
//   - 0 board cards missing : one deterministic evaluation.
//   - 1 or 2 missing        : EXACT enumeration of every runout.
//   - 3+ missing            : Monte Carlo, `n_samples` uniformly random
//                             runouts (partial Fisher-Yates, no repeats).
//
// Replaces the Python-side "replay the whole engine N times" loop used for
// Monte Carlo showdown averaging.
//
// FAST EVALUATOR (this version)
// -----------------------------
// Profiling showed ~19 us per sampled runout when scoring through
// evaluate_holdem_high (best-of-21 five-card combinations per hand). This
// file now carries a self-contained bitmask 7-card evaluator
// (fast_holdem_score) that classifies a hand in a few dozen operations,
// so a runout costs on the order of 100 ns instead of ~19 us.
//
// It is used ONLY to ORDER two hands against each other here (win / tie /
// loss); it is not the engine's scoring path and its numeric scores are
// meaningless outside this file. test_equity_mc.py cross-checks its
// win/tie/loss verdicts against poker_eval.evaluate_hands.
//
// Card ids follow the engine convention (rank = id % 13, 0 = deuce ...
// 12 = ace; suit = id / 13); masks are 52-bit with bit N set for card N,
// i.e. suit s occupies bits [13*s, 13*s + 12].
//
// Returned vector is {a_wins, ties, b_wins} (counts, not probabilities).

#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

namespace {

// ---------------------------------------------------------------------
// Bit helpers (portable across MSVC / GCC / Clang)
// ---------------------------------------------------------------------

inline int popcount32(uint32_t x) {
    x = x - ((x >> 1) & 0x55555555u);
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    return static_cast<int>((((x + (x >> 4)) & 0x0F0F0F0Fu) * 0x01010101u) >> 24);
}

inline int popcount64(uint64_t x) {
    int n = 0;
    while (x) { x &= x - 1; ++n; }
    return n;
}

// Index of the highest set bit. x must be non-zero.
inline int hibit(uint32_t x) {
#if defined(_MSC_VER)
    unsigned long i;
    _BitScanReverse(&i, static_cast<unsigned long>(x));
    return static_cast<int>(i);
#else
    return 31 - __builtin_clz(x);
#endif
}

// Highest set bit, or 0 if x == 0 (only used where x is non-empty for a
// legal 7-card hand; the guard just keeps the function total).
inline int hb(uint32_t x) { return x ? hibit(x) : 0; }

// ---------------------------------------------------------------------
// Straight detection on a 13-bit rank mask (bit r = rank r present).
// Returns the TOP rank index of the best straight (wheel A-2-3-4-5 has
// top rank 3, i.e. the five), or -1 if there is no straight.
// ---------------------------------------------------------------------
inline int straight_top(uint32_t m) {
    // ext bit 0 = ace-low, bits 1..13 = ranks 0..12
    const uint32_t ext = (m << 1) | ((m >> 12) & 1u);
    const uint32_t x = ext & (ext >> 1) & (ext >> 2) & (ext >> 3) & (ext >> 4);
    return x ? hibit(x) + 3 : -1;
}

// ---------------------------------------------------------------------
// 7-card (or 5/6-card) hold'em high-hand strength. Larger = better.
// score = category << 20 | up to five rank nibbles, most significant first.
// Categories: 8 straight flush, 7 quads, 6 full house, 5 flush, 4 straight,
// 3 trips, 2 two pair, 1 pair, 0 high card.
// ---------------------------------------------------------------------
inline uint32_t fast_holdem_score(uint64_t mask) {
    const uint32_t a = static_cast<uint32_t>(mask & 0x1FFFu);
    const uint32_t b = static_cast<uint32_t>((mask >> 13) & 0x1FFFu);
    const uint32_t c = static_cast<uint32_t>((mask >> 26) & 0x1FFFu);
    const uint32_t d = static_cast<uint32_t>((mask >> 39) & 0x1FFFu);
    const uint32_t ones = a | b | c | d;   // ranks present in any suit

    // Flush suit (with <= 7 cards at most one suit can hold 5+).
    uint32_t flush = 0;
    if (popcount32(a) >= 5)      flush = a;
    else if (popcount32(b) >= 5) flush = b;
    else if (popcount32(c) >= 5) flush = c;
    else if (popcount32(d) >= 5) flush = d;

    // 1. Straight flush
    if (flush) {
        const int sf = straight_top(flush);
        if (sf >= 0) return (8u << 20) | (static_cast<uint32_t>(sf) << 16);
    }

    // 2. Four of a kind
    const uint32_t fours = a & b & c & d;
    if (fours) {
        const int q = hibit(fours);
        const uint32_t rest = ones & ~(1u << q);
        return (7u << 20) | (static_cast<uint32_t>(q) << 16) |
               (static_cast<uint32_t>(hb(rest)) << 12);
    }

    const uint32_t threes = (a & b & c) | (a & b & d) | (a & c & d) | (b & c & d);
    const uint32_t twos   = (a & b) | (a & c) | (a & d) | (b & c) | (b & d) | (c & d);

    // 3. Full house (a second trips counts as the pair)
    if (threes) {
        const int t = hibit(threes);
        const uint32_t pairs = twos & ~(1u << t);
        if (pairs) {
            return (6u << 20) | (static_cast<uint32_t>(t) << 16) |
                   (static_cast<uint32_t>(hibit(pairs)) << 12);
        }
    }

    // 4. Flush: five highest ranks of the flush suit
    if (flush) {
        uint32_t m = flush;
        uint32_t packed = 0;
        for (int i = 0; i < 5; ++i) {
            const int r = hibit(m);
            packed = (packed << 4) | static_cast<uint32_t>(r);
            m &= ~(1u << r);
        }
        return (5u << 20) | packed;
    }

    // 5. Straight
    {
        const int st = straight_top(ones);
        if (st >= 0) return (4u << 20) | (static_cast<uint32_t>(st) << 16);
    }

    // 6. Three of a kind
    if (threes) {
        const int t = hibit(threes);
        uint32_t rest = ones & ~(1u << t);
        const int k1 = hibit(rest);
        rest &= ~(1u << k1);
        const int k2 = hb(rest);
        return (3u << 20) | (static_cast<uint32_t>(t) << 16) |
               (static_cast<uint32_t>(k1) << 12) | (static_cast<uint32_t>(k2) << 8);
    }

    // 7./8. Two pair / one pair  (no trips remain here, so `twos` = pairs)
    if (twos) {
        const int p1 = hibit(twos);
        const uint32_t rem = twos & ~(1u << p1);
        if (rem) {
            const int p2 = hibit(rem);
            const uint32_t kick_mask = ones & ~(1u << p1) & ~(1u << p2);
            return (2u << 20) | (static_cast<uint32_t>(p1) << 16) |
                   (static_cast<uint32_t>(p2) << 12) |
                   (static_cast<uint32_t>(hb(kick_mask)) << 8);
        }
        uint32_t rest = ones & ~(1u << p1);
        const int k1 = hibit(rest);
        rest &= ~(1u << k1);
        const int k2 = hibit(rest);
        rest &= ~(1u << k2);
        const int k3 = hb(rest);
        return (1u << 20) | (static_cast<uint32_t>(p1) << 16) |
               (static_cast<uint32_t>(k1) << 12) | (static_cast<uint32_t>(k2) << 8) |
               (static_cast<uint32_t>(k3) << 4);
    }

    // 9. High card: five highest ranks
    {
        uint32_t m = ones;
        uint32_t packed = 0;
        for (int i = 0; i < 5; ++i) {
            const int r = hb(m);
            packed = (packed << 4) | static_cast<uint32_t>(r);
            m &= ~(1u << r);
        }
        return packed;
    }
}

struct SplitMix64 {
    uint64_t state;
    explicit SplitMix64(uint64_t seed) : state(seed) {}
    inline uint64_t next() {
        uint64_t z = (state += 0x9E3779B97F4A7C15ULL);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }
    // Modulo bias is ~1e-18 for n <= 52; irrelevant here.
    inline uint32_t bounded(uint32_t n) { return static_cast<uint32_t>(next() % n); }
};

inline void tally(uint64_t hole_a, uint64_t hole_b, uint64_t full_board,
                  int64_t& a_wins, int64_t& ties, int64_t& b_wins) {
    const uint32_t sa = fast_holdem_score(hole_a | full_board);
    const uint32_t sb = fast_holdem_score(hole_b | full_board);
    if (sa > sb)       ++a_wins;
    else if (sa < sb)  ++b_wins;
    else               ++ties;
}

}  // namespace


std::vector<int64_t> holdem_matchup_counts(
    uint64_t hole_a,
    uint64_t hole_b,
    uint64_t board_mask,
    int n_samples,
    uint64_t seed)
{
    if (popcount64(hole_a) != 2 || popcount64(hole_b) != 2)
        throw std::invalid_argument("holdem_matchup_counts: each hole mask must have exactly 2 cards");
    if ((hole_a & hole_b) || (hole_a & board_mask) || (hole_b & board_mask))
        throw std::invalid_argument("holdem_matchup_counts: hole/board masks overlap");

    const int board_n = popcount64(board_mask);
    if (board_n > 5)
        throw std::invalid_argument("holdem_matchup_counts: board has more than 5 cards");
    const int need = 5 - board_n;

    int64_t a_wins = 0, ties = 0, b_wins = 0;

    if (need == 0) {
        tally(hole_a, hole_b, board_mask, a_wins, ties, b_wins);
        return {a_wins, ties, b_wins};
    }

    const uint64_t used = hole_a | hole_b | board_mask;
    int avail[52];
    int n_avail = 0;
    for (int c = 0; c < 52; ++c)
        if (!((used >> c) & 1ULL)) avail[n_avail++] = c;

    if (need == 1) {
        for (int i = 0; i < n_avail; ++i)
            tally(hole_a, hole_b, board_mask | (1ULL << avail[i]), a_wins, ties, b_wins);
        return {a_wins, ties, b_wins};
    }

    if (need == 2) {
        for (int i = 0; i < n_avail; ++i)
            for (int j = i + 1; j < n_avail; ++j)
                tally(hole_a, hole_b,
                      board_mask | (1ULL << avail[i]) | (1ULL << avail[j]),
                      a_wins, ties, b_wins);
        return {a_wins, ties, b_wins};
    }

    if (n_samples < 1)
        throw std::invalid_argument("holdem_matchup_counts: n_samples must be >= 1 for 3+ missing board cards");

    SplitMix64 rng(seed);
    for (int s = 0; s < n_samples; ++s) {
        // Partial Fisher-Yates over `avail`. The array is NOT restored
        // between samples: re-shuffling an already-shuffled array is still
        // a uniform random permutation, so every sample stays unbiased.
        uint64_t full = board_mask;
        for (int k = 0; k < need; ++k) {
            const uint32_t pick = k + rng.bounded(static_cast<uint32_t>(n_avail - k));
            const int tmp = avail[k];
            avail[k] = avail[pick];
            avail[pick] = tmp;
            full |= (1ULL << avail[k]);
        }
        tally(hole_a, hole_b, full, a_wins, ties, b_wins);
    }
    return {a_wins, ties, b_wins};
}


// Batched form: one Python->C++ crossing for many matchups (e.g. every
// showdown hand in a rollout batch). Matchup i uses seed + i * golden-ratio
// constant so results are reproducible but independent across matchups.
std::vector<std::vector<int64_t>> holdem_matchup_counts_batch(
    const std::vector<uint64_t>& holes_a,
    const std::vector<uint64_t>& holes_b,
    const std::vector<uint64_t>& boards,
    int n_samples,
    uint64_t seed)
{
    if (holes_a.size() != holes_b.size() || holes_a.size() != boards.size())
        throw std::invalid_argument("holdem_matchup_counts_batch: input vectors must have equal length");

    std::vector<std::vector<int64_t>> out;
    out.reserve(holes_a.size());
    for (size_t i = 0; i < holes_a.size(); ++i) {
        out.push_back(holdem_matchup_counts(
            holes_a[i], holes_b[i], boards[i], n_samples,
            seed + static_cast<uint64_t>(i) * 0x9E3779B97F4A7C15ULL));
    }
    return out;
}