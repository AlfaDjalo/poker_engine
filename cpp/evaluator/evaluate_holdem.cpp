#include "card_utils.hpp"
#include "comb_tables.hpp"
#include "five_card_rank.hpp"

#include <utility>
#include <vector>

std::pair<int, uint64_t> evaluate_holdem_high(
    uint64_t hole_mask,
    uint64_t board_mask
)
{
    auto hole = mask_to_cards(hole_mask);
    auto board = mask_to_cards(board_mask);

    std::vector<int> all = hole;
    all.insert(all.end(), board.begin(), board.end());

    int n = all.size();

    auto combos = choose(n, 5);

    int best = -1;
    uint64_t best_mask = 0;

    for (auto& c: combos)
    {
        uint64_t m =
            make_mask5(
                all[c[0]],
                all[c[1]],
                all[c[2]],
                all[c[3]],
                all[c[4]]
            );

        int s = rank_high_5(m);

        if (s > best) { best = s; best_mask = m; }
    }

    return {best, best_mask};
}