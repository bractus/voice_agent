"""Contract tests never reach the network: the resume reader is always faked here."""
import pytest


@pytest.fixture(autouse=True)
def _no_real_resume_reader(fake_resume_reader):
    return fake_resume_reader
