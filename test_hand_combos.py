from constraints.types import bit
from constraints.generator import generate_k_submasks

hole_mask = bit(0) | bit(1)
board_mask = bit(2) | bit(3) | bit(4) | bit(5) | bit(6)

hole_combos = generate_k_submasks(hole_mask, 2)
board_combos = generate_k_submasks(board_mask, 3)

valid_hands = [
    h | b
    for h in hole_combos
    for b in board_combos
]

print(valid_hands)