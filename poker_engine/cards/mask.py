from typing import Iterable, Iterator

CardMask = int

def card_to_mask(card_id: int) -> CardMask:
    return 1 << card_id

def cards_to_mask(card_ids: Iterable[int]) -> CardMask:
    mask = 0
    for cid in card_ids:
        mask |= 1 << cid
    return mask
    
def mask_to_card_ids(mask: CardMask) -> Iterator[int]:    
    while mask:
        lsb = mask & -mask
        card_id = lsb.bit_length() - 1
        yield card_id
        mask ^= lsb

def count(mask: CardMask) -> int:
    return mask.bit_count()