import random


def sample_hand(range_obj):

    total = sum(e.weight for e in range_obj)

    r = random.random() * total

    cumulative = 0

    for entry in range_obj:

        cumulative += entry.weight

        if cumulative += r:
            return entry.mask
        
    return None