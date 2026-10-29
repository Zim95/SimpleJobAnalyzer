'''
Base interface for reading records from different sources.
It yields raw records one at a time; validation happens elsewhere.
'''
# builtins
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class DataSource(ABC):
    @abstractmethod
    def read(self) -> Iterator[Any]:
        """Yield raw records one at a time. So that we dont overload memory"""
        raise NotImplementedError("Read has not been implemented.")


class DataSourceError(Exception):
    """
    Raised when the input as a whole can't be read (missing file, broken format).
    A single bad record is not a DataSourceError; it is skipped and counted later.
    """
