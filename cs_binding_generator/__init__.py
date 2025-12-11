"""
C# Bindings Generator - Generate C# P/Invoke bindings from C header files
"""

from .generator import CSharpBindingsGenerator
from .type_mapper import TypeMapper
from .code_generators import CodeGenerator, OutputBuilder
from .constants import (
    CSHARP_TYPE_MAP,
    REQUIRED_USINGS,
    DEFAULT_NAMESPACE,
    NATIVE_METHODS_CLASS,
)

__version__ = "0.1.0"

__all__ = [
    "CSharpBindingsGenerator",
    "TypeMapper",
    "CodeGenerator",
    "OutputBuilder",
    "CSHARP_TYPE_MAP",
    "REQUIRED_USINGS",
    "DEFAULT_NAMESPACE",
    "NATIVE_METHODS_CLASS",
]
