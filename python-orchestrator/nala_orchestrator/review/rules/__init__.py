from .base import ReviewRule
from .react_hooks import react_rules
from .error_handling import error_rules
from .concurrency import concurrency_rules
from .security import security_rules
from .unused import unused_rules
from .consistency import consistency_rules

ALL_RULES = (
    react_rules +
    error_rules +
    concurrency_rules +
    security_rules +
    unused_rules +
    consistency_rules
)
