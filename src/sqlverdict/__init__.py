from sqlverdict._version import __version__
from sqlverdict.compare import compare, to_result
from sqlverdict.model import Result, Verdict

__all__ = ["compare", "to_result", "Result", "Verdict", "__version__"]
