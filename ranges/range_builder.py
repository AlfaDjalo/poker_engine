from itertools import combinations

from cards.mask import card_to_mask
from cards.suit_iso import canonicalize_state
from ranges.hand_range import HandRange


def build_holdem_range():

    r = HandRange()

    for c1, c2 in combinations(range(52), 2):

        mask = card_to_mask(c1) | card_to_mask(c2)

        holes, _ = canonicalize_state([mask], 0)

        canon = holes[0]

        r.add(canon)

    return r

def build_omaha_range():

    r = HandRange()

    for combo in combinations(range(52), 4):

        mask = 0

        for c in combo:
            mask |= card_to_mask(c)

        holes, _ = canonicalize_state([mask], 0)

        canon = holes[0]

        r.add(canon)

    return r
