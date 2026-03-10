#include "card_utils.hpp"
#include "comb_tables.hpp"
#include "five_card_rank.hpp"

#include <vector>

int evaluate_draw_high(uint64_t hand_mask)
{
    auto cards = mask_to_cards(hand_mask);

    auto combos = choose(cards.size(), 5);

    int best = -1;

    for (auto& c:combos)
    {
        uint64_t mask =
            make_mask5(
                cards[c[0]],
                cards[c[1]],
                cards[c[2]],
                cards[c[3]],
                cards[c[4]]
            );

        int s = rank_high_5(mask);

        if (s > best) best = s;
    }

    return best;
}