#include "card_utils.hpp"
#include "comb_tables.hpp"
#include "five_card_rank.hpp"

#include <vector>

int evaluate_omaha_high(
    uint64_t hole_mask,
    uint64_t board_mask
)
{
    auto hole = mask_to_cards(hole_mask);
    auto board = mask_to_cards(board_mask);

    auto hole2 = choose(hole.size(), 2);
    auto board3 = choose(board.size(), 3);

    int best = -1;

    for (auto& h:hole2)
    {
        uint64_t hm =
            (1ULL<<hole[h[0]]) |
            (1ULL<<hole[h[1]]);

        for (auto& b:board3)
        {
            uint64_t bm =
                (1ULL<<board[b[0]]) |
                (1ULL<<board[b[1]]) |
                (1ULL<<board[b[2]]);

            uint64_t mask = hm | bm;

            int s = rank_high_5(mask);

            if (s > best) best = s;
        }
    }

    return best;
}