import pytest

from app.core.errors import AppError
from app.moderation.consent import require_consent


def test_require_consent_raises_when_false():
    with pytest.raises(AppError):
        require_consent(False)


def test_require_consent_returns_a_timestamp_when_true():
    result = require_consent(True)
    assert isinstance(result, str)
    assert result.endswith("Z")
