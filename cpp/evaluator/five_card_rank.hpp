#pragma once
#include <cstdint>
#include <array>
#include <algorithm>

inline int rank_of(int card)
{
    return card % 13;
}

inline int suit_of(int card)
{
    return card / 13;
}

inline int rank_high_5(uint64_t mask)
{
    std::array<int, 5> ranks;
    std::array<int, 5> suits;

    int idx = 0;

    for (int i = 0; i < 52; i++)
    {
        if (mask&(1ULL<<i))
        {
            ranks[idx] = rank_of(i);
            suits[idx] = suit_of(i);
            idx++;
        }
    }

    std::sort(ranks.begin(), ranks.end());

    bool flush = true;
    for (int i = 1; i < 5; i++)
        if (suits[i] != suits[0]) flush = false;

    bool straight = true;
    for (int i = 1; i < 5; i++)
        if (ranks[i] != ranks[0] + i) straight = false;

    int score = 0;

    for (int r: ranks)
        score = score * 13 + r;

    if (straight && flush) score += 9000000;
    else if (flush) score += 6000000;
    else if (straight) score += 5000000;

    return score;
}