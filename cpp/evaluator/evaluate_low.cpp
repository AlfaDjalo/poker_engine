#include "evaluate_low.h"
#include "five_card_rank.hpp"

#include <vector>
#include <cstdint>
#include <algorithm>
#include <array>

namespace poker_eval {

// --------------------------------------------------
// Card utilities
// --------------------------------------------------

static void mask_to_cards(uint64_t mask, std::vector<int>& cards) {
    cards.clear();
    for (int i = 0; i < 52; i++)
        if (mask & (1ULL << i))
            cards.push_back(i);
    // while (mask) {
    //     uint64_t lsb = mask & (-mask);
    //     int card = lsb.bit_length() - 1;
    //     int bit = 0;
    //     uint64_t tmp = lsb;
    //     while (tmp > 1) { tmp >>= 1; ++bit; }
    //     cards.push_back(bit);
    //     mask ^= lsb;
    // }
}

// Encode a 5-card low-A5 hand as a comparable uint32.
// Ranks: Ace=1, 2=2, ..., King=13.
// Packs highest rank in MSB so lower value = better hand.
// Returns 0 if hand has a pair (invalid low).
static uint32_t encode_a5_low(const std::array<int, 5>& card_ids) {
    std::array<int, 5> ranks;
    for (int i = 0; i < 5; i++) {
        int r = card_ids[i] % 13;
        ranks[i] = (r == 12) ? 1 : r + 2; // Ace = 1, 2 = 2, ... King = 13
    }
    std::sort(ranks.begin(), ranks.end());
    // Reject pairs
    for (int i = 1; i < 5; i++)
        if (ranks[i] == ranks[i - 1]) return 0;
    // Pack: highest rank in MSB (bits 16-19), lowest in LSBB (bits 0-3)
    uint32_t v = 0;
    for (int i = 4; i >= 0; i--)
        v = (v << 4) | (ranks[i] & 0xF);
    return v;
}

// For LOW_27 we reuse rank_high_5 directly.
// A lower high-hand score means a better low hand,
// so the caller uses min() to find the winner.
// We just need to verify the hand has no qualifier violations — 
// that is handled in Python via the qualifier check.

// Generate all combinations of k indices from n
static void combinations(int n, int k,
    std::vector<std::array<int, 5>>& out,
    std::array<int, 5>& buf, int start, int depth)
{
    if (depth == k) { out.push_back(buf); return; }
    for (int i = start; i < n; i++) {
        buf[depth] = i;
        combinations(n, k, out, buf, i+1, depth+1);
    }
}    

// Gather all 5-card combinations from hole+board
// according to ShowdownType rules
static std::vector<std::array<int, 5>> get_five_card_combos(
    const std::vector<int>& hole,
    const std::vector<int>& board,
    int showdown_type // 0=HOLDEM, 1=OMAHA, 2=MAKE5, 3=DRAW
)
{
    std::vector<std::array<int, 5>> result;
    std::array<int, 5> buf{};

    if (showdown_type == 3) {
        // DRAW: 5 hole cards, no board
        if ((int)hole.size() < 5) return result;
        combinations(hole.size(), 5, result, buf, 0, 0);
        // map indices to card_ids
        for (auto& combo: result)
            for (int i=0; i < 5; i++)
                combo[i] = hole[combo[i]];
        return result;
    }

    if (showdown_type == 1) {
        // OMAHA: exactly 2 hole + 3 board
        if ((int)hole.size() < 2 || (int)board.size() < 3) return result;
        for (int i = 0; i+1 < (int)hole.size(); i++)
        for (int j = i+1; j < (int)hole.size(); j++)
        for (int a = 0; a+2 < (int)board.size(); a++)
        for (int b = a+1; b+1 < (int)board.size(); b++)
        for (int c = b+1; c < (int)board.size(); c++)
            result.push_back({hole[i], hole[j], board[a], board[b], board[c]});
        return result;
    }

    if (showdown_type == 0) {
        // HOLDEM: best 5 from all available cards
        std::vector<int> all;
        all.insert(all.end(), hole.begin(), hole.end());
        all.insert(all.end(), board.begin(), board.end());
        if ((int)all.size() < 5) return result;
        std::vector<std::array<int, 5>> idx_combos;
        combinations(all.size(), 5, idx_combos, buf, 0, 0);
        for (auto& combo : idx_combos) {
            std::array<int, 5> cards{};
            for (int i = 0; i < 5; i++) cards[i] = all[combo[i]];
            result.push_back(cards);
        }
        return result;
    }

    if (showdown_type == 2) {
        // MAKE5: all board cards and enough board cards to make 5 card hand
    }

    if (showdown_type == 4) {
        // BADUGI
    }

}


// // A5: Ace = 1, ignore straights/flushes
// static int a5_rank(int card_id) {
//     int r = card_id % 13;
//     return (r == 12) ? 1 : r + 2;
// }

// // 27: Ace = 14, straights and flushes count against you
// static int low27_rank(int card_id) {
//     int r = card_id % 13;
//     return (r == 12) ? 14 : r + 2;
// }

// static int card_suit(int card_id) {
//     return card_id / 13;
// }

// static bool is_straight(const std::array<int, 5>& s) {
//     // s is sorted ascending
//     return (s[4] - s[0] == 4) &&
//     (s[1]==s[0]+1) && (s[2]==s[0]+2) && (s[3]==s[0]+3);
// }

// static bool is_flush(const std::array<int,5>& suits) {
//     return suits[0]==suits[1] && suits[1]==suits[2] &&
//             suits[2]==suits[3] && suits[3]==suits[4];
// }
// // Returns low rank value: Ace=1, 2=2, ..., King=13
// // static int low_card_rank(int card_id) {
// //     int rank_index = card_id % 13;
// //     if (rank_index == 12) return 1;     // Ace low
// //     return rank_index + 2;
// // }

// // --------------------------------------------------
// // Encoding
// // Packs 5 ranks (sorted ascending) into a uint32_t.
// // Each rank fits in 4 bits (max rank = 13 = 0xD).
// // Lowest rank (best card) in most significant nibble.
// // Lower encoded value = better low hand.
// // The highest rank (worst card) is in the least significant nibble —
// // this is what we test against the 8-or-better qualifier.
// // --------------------------------------------------
// static uint32_t encode_low_hand(const std::array<int, 5>& sorted_ranks) {
//     uint32_t value = 0;
//     for (int i = 4; i >= 0; --i) {
//         value = (value << 4) | static_cast<uint32_t>(sorted_ranks[i] & 0xF);
//     }

//     return value;
// }

// // --------------------------------------------------
// // Validation
// // For low hands, ensure no pairs (strictly ascending ranks).
// // No rank limit enforced here; qualification happens in Python.
// // --------------------------------------------------
// static bool is_valid_low(const std::array<int, 5>& sorted_ranks) {
//     for (int i = 1; i < 5; ++i) {
//         if (sorted_ranks[i] == sorted_ranks[i-1]) return false;
//     }
//     return true;
// }

// // --------------------------------------------------
// // Core evaluator
// // Returns encoded low hand (lower = better),
// // or 0 if no valid low hand exists.
// // --------------------------------------------------
// static uint32_t evaluate_low_internal(uint64_t hole_mask, uint64_t board_mask) {
//     std::vector<int> hole_cards;
//     std::vector<int> board_cards;

//     mask_to_cards(hole_mask, hole_cards);
//     mask_to_cards(board_mask, board_cards);

//     if (hole_cards.size() < 2 || board_cards.size() < 3) {
//         return 0;
//     }

//     uint32_t best = 0;
//     bool found = false;
//     std::array<int, 5> low_hand{};

//     for (size_t i = 0; i + 1 < hole_cards.size(); ++i) {
//         for (size_t j = i + 1; j < hole_cards.size(); ++j) {
//             low_hand[0] = low_card_rank(hole_cards[i]);
//             low_hand[1] = low_card_rank(hole_cards[j]);

//             for (size_t a = 0; a + 2 < board_cards.size(); ++a) {
//                 for (size_t b = a + 1; b + 1 < board_cards.size(); ++b) {
//                     for (size_t c = b + 1; c < board_cards.size(); ++c) {
//                         low_hand[2] = low_card_rank(board_cards[a]);
//                         low_hand[3] = low_card_rank(board_cards[b]);
//                         low_hand[4] = low_card_rank(board_cards[c]);

//                         std::sort(low_hand.begin(), low_hand.end());

//                         if (!is_valid_low(low_hand)) continue;

//                         uint32_t score = encode_low_hand(low_hand);

//                         if (!found || score < best) {
//                             best = score;
//                             found = true;
//                         }
//                     }
//                 }
//             }
//         }
//     }

//     return found ? best : 0;
// }

// --------------------------------------------------
// Public API
// --------------------------------------------------

// LOW_A5: Ace=low, straights/flushes ignored, lower_score = better
uint64_t evaluate_low_a5(uint64_t hole_mask, uint64_t board_mask, int showdown_type) {
    std::vector<int> hole, board;
    mask_to_cards(hole_mask, hole);
    mask_to_cards(board_mask, board);

    auto combos = get_five_card_combos(hole, board, showdown_type);

    uint32_t best = 0;
    for (auto& cards : combos) {
        uint32_t score = encode_a5_low(cards);
        if (score == 0) continue; // paired hand
        if (best == 0 || score < best)
            best = score;
    }
    return best;
}

// LOW_27: Ace=high, straights/flushes count against you.
// We reuse rank_high_5 — a lower high-hand score = better low hand.
// Caller uses min() to find winner.
uint64_t evaluate_low_27(uint64_t hole_mask, uint64_t board_mask, int showdown_type) {
    std::vector<int> hole, board;
    mask_to_cards(hole_mask, hole);
    mask_to_cards(board_mask, board);

    auto combos = get_five_card_combos(hole, board, showdown_type);

    uint32_t best = 0;
    for (auto& cards : combos) {
        uint32_t mask = 0;
        for (int c : cards) mask |= (1ULL << c);
        int score = rank_high_5(mask);
        if (score <= 0) continue;
        if (best == 0 || (uint64_t)score < best)
            best = (uint64_t)score;
    }
    return best;
}

}  // namespace poker_eval
