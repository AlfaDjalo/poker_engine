#pragma once

#include <string>
#include <vector>
#include <cstdint>

namespace cards {

    using CardMask = uint64_t;

    /*
    Rank order:
    0 = 2
    1 = 3
    ...
    8 = T
    9 = J
    10 = Q
    11 = K
    12 = A
    */

    int rank_index(char r);
    int suit_index(char s);

    CardMask card_to_mask(const std::string& card);

    CardMask cards_to_mask(const std::vector<std::string>& cards);

    std::vector<std::string> mask_to_cards(CardMask mask);

    int popcount(CardMask mask);
    
}