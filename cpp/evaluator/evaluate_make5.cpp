#include "card_utils.hpp"
#include "comb_tables.hpp"
#include "five_card_rank.hpp"

#include <vector>

int evaluate_make5_high(
    uint64_t hole_mask,
    uint64_t board_mask
)
{
    auto hole = mask_to_cards(hole_mask);
    auto board = mask_to_cards(board_mask);

    int need = 5 - board.size();

    auto combos = choose(hole.size(), need);

    int best = -1;

    for (auto& c:combos)
    {
        uint64_t mask = board_mask;

        for (int idx:c)
            mask |= (1ULL<<hole[idx]);

        int s = rank_high_5(mask);

        if (s > best) best = s;
    }

    return best;
}