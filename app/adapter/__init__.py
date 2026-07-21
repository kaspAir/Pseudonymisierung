"""Anbieter-Adapter. Nur hier darf Protokollwissen eines Anbieters liegen."""
from . import anthropic, voyage           # noqa: F401  (Registrierung)
from .basis import Adapter, alle, hole, registriere   # noqa: F401
