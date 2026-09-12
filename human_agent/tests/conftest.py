import copy
import pytest
from scripts.make_examples import normal
from app.schemas import AnalyzeRequest

@pytest.fixture
def raw(): return normal()

@pytest.fixture
def snapshot(raw): return AnalyzeRequest.model_validate(raw)
