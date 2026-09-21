from __future__ import annotations

import pytest

from src.data_loader import load_catalog


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()
