from cards.mask import card_to_mask
from ranges.range_builder import build_holdem_range

board = (
    card_to_mask(12) |
    card_to_mask(25) |
    card_to_mask(38)
)

r = build_holdem_range()

r.remove_blocked(board)

print(len(r))