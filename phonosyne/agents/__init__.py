"""
Phonosyne Agents Subpackage

This module initializes the `phonosyne.agents` subpackage.
It will export the core agent classes (Designer, Analyzer, Compiler)
and any Pydantic schemas used for data validation and transfer between agents.

Key features:
- Marks the 'phonosyne/agents' directory as a Python subpackage.
- Will export AgentBase, DesignerAgent, AnalyzerAgent, CompilerAgent.
- Will export Pydantic schemas like MovementStub, SampleStub, AnalyzerOut.

@dependencies
- Modules within this subpackage (e.g., `base`, `designer`, `analyzer`, `compiler`, `schemas`).

@notes
- Exports will be added as the respective components are implemented.
"""

# TODO: Import and export AnalyzerAgent from .analyzer (Step 3.3)
from .analyzer import AnalyzerAgent

# TODO: Import and export AgentBase from .base (Step 3.1)
from .base import AgentBase

# TODO: Import and export CompilerAgent from .compiler (Step 3.4)
from .compiler import CompilerAgent

# TODO: Import and export DesignerAgent from .designer (Step 3.2)
from .designer import DesignerAgent, DesignerAgentInput

# TODO: Import and export Pydantic schemas from .schemas (Step 2.2)
from .schemas import (
    AnalyzerInput,
    AnalyzerOutput,
    DesignerOutput,
    MovementStub,
    SampleStub,
)

__all__ = [
    "AgentBase",
    "DesignerAgent",
    "DesignerAgentInput",
    "AnalyzerAgent",
    "CompilerAgent",
    "MovementStub",
    "SampleStub",
    "DesignerOutput",
    "AnalyzerInput",
    "AnalyzerOutput",
]
