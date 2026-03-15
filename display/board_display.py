from cards.card import Card


def format_cap_boards(node_cards, row_length=5):
    """
    Format CAP-style boards for terminal display.

    Assumes:
        nodes 0 - row_length-1                      -> board 1
        nodes row_length - 2 * row_length - 1       -> board 2
        nodes 2 * row_length - 3 * row_length - 1   -> board 3
    """

    if not node_cards:
        return "Board: (no board)"
    
    lines = []

    # Split nodes into rows of row_length
    for start in range(0, len(node_cards), row_length):

        row = node_cards[start:start + row_length]

        # stop if row is completely empty
        if all(c is None for c in row):
            continue

        cards = []

        for c in row: 
            if c is None:
                cards.append("--")
            else:
                cards.append(str(Card(c)))

        lines.append(" ".join(cards))

    if not lines:
        return "Board: (no board)"
    
    return "\n".join(lines)