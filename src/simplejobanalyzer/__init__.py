'''
SimpleJobAnalyzer: summarise job execution records.

Entry point for the `simplejobanalyzer` command ([project.scripts] in pyproject.toml).
'''
from simplejobanalyzer.cli import run

__all__ = ["run"]
