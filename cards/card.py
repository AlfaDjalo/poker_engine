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
        rank = s[0]
        suit = s[1]

        r = RANKS.index(rank)
        s_index = SUITS.index(suit)

        return Card(s_index * 13 + r)