from typing import Iterable
from constraints.types import NodeMask


def iterate_bits(mask: NodeMask):
    """
    Yield each single-bit mask from a mask.
    """
    while mask:
        lsb = mask & -mask
        yield lsb
        mask ^= lsb


def choose_k(mask: NodeMask, k: int) -> Iterable[NodeMask]:
    """
    Generate all submasks of `mask` containing exactly k bits.
    
    Recursive implementation that avoids enumerating all subsets.
    """

    bits = list(iterate_bits(mask))
    n = len(bits)

    if k > n:
        return
    
    def dfs(start, remaining, current):
        if remaining == 0:
            yield current
            return
        
        for i in range(start, n):
            yield from dfs(
                i + 1,
                remaining - 1,
                current | bits[i]
            )

    yield from dfs(0, k, 0)