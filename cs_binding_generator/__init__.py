"""
C# Bindings Generator - Generate C# P/Invoke bindings from C header files
"""

from .code_generators import CodeGenerator, OutputBuilder
from .constants import (CSHARP_TYPE_MAP, DEFAULT_NAMESPACE,
                        NATIVE_METHODS_CLASS, REQUIRED_USINGS)
from .generator import CSharpBindingsGenerator
from .type_mapper import TypeMapper

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

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
