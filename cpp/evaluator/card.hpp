#pragma once
#include <cstdint>

static const int PRIMES[13] = {
    2, 3, 5, 7, 11, 13, 17,
    19, 23, 29, 31, 37, 41
};

inline uint32_t make_card(int rank, int suit)
{
    return
        (PRIMES[rank] << 16) |
        (rank << 8) |
        (1 << (suit + 12)) |
        (1 << rank);
}