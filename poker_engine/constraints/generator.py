from typing import Iterable, List
from .types import NodeMask

def generate_submasks(mask: NodeMask) -> Iterable[NodeMask]:
    """
    Yield all non-zero submasks of mask.
    """
    sub = mask
    while sub:
        yield sub
        sub = (sub - 1) & mask

def generate_k_submasks(mask: NodeMask, k: int) -> List[NodeMask]:
    """
    Generate all submasks of `mask` with exactly k bits set.
    """
    results = []
    sub = mask
    while sub:
        if sub.bit_count() == k:
            results.append(sub)
        sub = (sub - 1) & mask
    return results