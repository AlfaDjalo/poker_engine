from typing import List
from .mask import CardMask, mask_to_card_ids
from .card import Card

def mask_to_card_strings(mask: CardMask) -> List[str]:
    """Convert a card bitmask to a list of card strings (e.g. ['As', 'Kd', 'Qh'])."""
    return [str(Card(card_id)) for card_id in mask_to_card_ids(mask)]

def mask_to_card_string(mask: CardMask) -> str:
    """Convert a card bitmask to a single comma-separated string (e.g. 'As,Kd,Qh')."""
    return ",".join(mask_to_card_strings(mask))
