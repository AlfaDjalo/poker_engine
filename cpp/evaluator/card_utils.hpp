#pragma once
#include <vector>
#include <cstdint>

inline std::vector<int> mask_to_cards(uint64_t mask)
{
    std::vector<int> cards;

    for (int i = 0; i < 52; i++)
    {
        if (mask & (1ULL << i))
            cards.push_back(i);
    }

    return cards;
}

inline uint64_t cards_to_mask(const std::vector<int>& cards)
{
    uint64_t mask = 0;

    for (int c : cards)
        mask |= (1ULL << c);

    return mask;
}

inline uint64_t make_mask5(int a, int b, int c, int d, int e)
{
    return
        (1ULL<<a) |
        (1ULL<<b) |
        (1ULL<<c) |
        (1ULL<<d) |
        (1ULL<<e);
}