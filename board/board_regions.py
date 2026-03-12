def board_cards_after_street(board_cards_per_street, street_index):
    """
    Total number of board cards after given street.
    """
    return sum(board_cards_per_street[:street_index + 1])