from dataclasses import dataclass
from .action_type import ActionType

@dataclass(frozen=True)
class Action:

    type: ActionType
    amount: int = 0

    def __repr__(self):
       return f"{self.type.name}({self.amount})"
    