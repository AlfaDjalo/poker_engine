#include "eval5.hpp"
#include <cstdint>

/*
These tables must be generated once.
For brevity they are declared here but must be filled with
the standard Cactus Kev lookup tables.
*/

extern int flush_lookup[8192];
extern int unsuited_lookup[4888];

inline int hash(uint32_t key)
{
    key += 0xe91aaa35;
    key ^= key >> 16;
    key += key << 8;
    key ^= key >> 4;
    return key & 0x1FFF;
}

int eval5(uint32_t c1,
            uint32_t c2,
            uint32_t c3,
            uint32_t c4,
            uint32_t c5)
{
    uint32_t suit_mask = 
        c1 & c2 & c3 & c4 & c5 & 0xF000;

    uint32_t rank_bits =
        (c1 | c2 | c3 | c4 | c5) & 0x1FFF;

    if (suit_mask)
        return flush_lookup[rank_bits];

    uint32_t prime_product =
        (c1 >> 16) *
        (c2 >> 16) *
        (c3 >> 16) *
        (c4 >> 16) *
        (c5 >> 16);

    return unsuited_lookup[hash(prime_product)];
}