"""Background job utilities for the music pipeline."""

# Ensure RQ can resolve jobs.tasks.* by importing the submodule.
from . import tasks  # noqa: F401
