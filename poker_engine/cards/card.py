from dataclasses import dataclass

RANKS = "23456789TJQKA"
SUITS = "cdhs" # clubs, diamonds, hearts, spades

@dataclass(frozen=True)
class Card:
    id: int

    @property
    def rank(self) -> str:
        return RANKS[self.id % 13]
    
    @property
    def suit(self) -> str:
        return SUITS[self.id // 13]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"
    
    @staticmethod
    def from_str(s: str) -> "Card":
        if not isinstance(s, str) or len(s) != 2:
            raise ValueError(f"Invalid card string: {s!r} (expected 2 chars, e.g. 'Ah')")

        rank = s[0].upper()
        suit = s[1].lower()

        if rank not in RANKS:
            raise ValueError(f"Invalid card string: {s!r} (unknown rank {rank!r})")
        if suit not in SUITS:
            raise ValueError(f"Invalid card string: {s!r} (unknown suit {suit!r})")

        r = RANKS.index(rank)
        s_index = SUITS.index(suit)

        return Card(s_index * 13 + r)