"""
Pytest configuration and fixtures.

This module mocks spacy before any test imports to avoid pydantic v1 
compatibility issues with Python 3.14.
"""
import sys
from unittest.mock import MagicMock

# Mock spacy and spacy-related modules before any other imports
# This prevents pydantic v1 compatibility errors with Python 3.14
spacy_mock = MagicMock()
sys.modules['spacy'] = spacy_mock
sys.modules['spacy.language'] = MagicMock()
sys.modules['spacy.pipeline'] = MagicMock()
sys.modules['spacy.tokens'] = MagicMock()
sys.modules['spacy.vocab'] = MagicMock()
sys.modules['spacy.pipe_analysis'] = MagicMock()
