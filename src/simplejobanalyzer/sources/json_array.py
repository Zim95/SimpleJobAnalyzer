'''
Reads a file containing one JSON array of records.

ijson parses by JSON structure, not by lines, so pretty-printed and minified files
both work, and only one record is held in memory at a time whatever the file size.
'''
# builtins
from typing import Iterator, Any

# third party
import ijson  # type: ignore[import-untyped]  # ijson ships no type hints

# modules
from .base import DataSource, DataSourceError


class JsonArraySource(DataSource):
    def __init__(self, path: str) -> None:
        self.path = path

    def read(self) -> Iterator[Any]:
        try:
            with open(self.path, "rb") as f:
                # ijson.items(f, "item") silently yields nothing for a top-level
                # object, so check that the file really starts with an array.
                if f.read(64).lstrip()[:1] != b"[":
                    raise DataSourceError(f"{self.path} must contain a JSON array")
                f.seek(0)
                # "item" = each element of the top-level array.
                # use_float=True returns floats instead of Decimal.
                yield from ijson.items(f, "item", use_float=True)
        except ijson.JSONError as e:
            raise DataSourceError(f"{self.path} is not a valid JSON array: {e}") from e
        except OSError as e:
            raise DataSourceError(f"cannot read {self.path}: {e}") from e
