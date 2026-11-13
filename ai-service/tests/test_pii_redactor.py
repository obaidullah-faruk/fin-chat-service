from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from security.pii_redactor import (
    DEFAULT_REPLACEMENTS,
    PresidioPIIRedactor,
    RedactedEntity,
    RedactionResult,
    RegexPIIRedactor,
    get_pii_redactor,
    is_pii_present,
    redact_pii,
    redact_text,
    set_pii_redactor,
)


@pytest.fixture(autouse=True)
def reset_redactor_instance():
    """Ensure tests run against a clean redactor state."""
    yield
    set_pii_redactor(None)


def test_regex_redact_finchat_account_number():
    redactor = RegexPIIRedactor()
    text = "What is the balance of my account FC1000000001?"
    result = redactor.redact(text)

    assert result.has_pii is True
    assert result.redacted_text == "What is the balance of my account <ACCOUNT_NUMBER>?"
    assert len(result.entities) == 1
    assert result.entities[0].entity_type == "BANK_ACCOUNT"
    assert result.entities[0].text == "FC1000000001"


def test_regex_redact_contextual_account_number():
    redactor = RegexPIIRedactor()
    text = "Check transactions for Account no: 987654321012 immediately"
    result = redactor.redact(text)

    assert result.has_pii is True
    assert "<ACCOUNT_NUMBER>" in result.redacted_text
    assert "987654321012" not in result.redacted_text


def test_regex_redact_bangladeshi_nid_17_digits():
    redactor = RegexPIIRedactor()
    text = "My national identity is 19901234567890123, verify my KYC."
    result = redactor.redact(text)

    assert result.has_pii is True
    assert result.redacted_text == "My national identity is <ID_NUMBER>, verify my KYC."
    assert result.entities[0].entity_type == "BD_NID"
    assert result.entities[0].text == "19901234567890123"


def test_regex_redact_bangladeshi_nid_13_and_10_digits():
    redactor = RegexPIIRedactor()
    text_13 = "My NID is 1234567890123 please update KYC."
    result_13 = redactor.redact(text_13)
    assert result_13.has_pii is True
    assert result_13.redacted_text == "My NID is <ID_NUMBER> please update KYC."

    text_10 = "voter id: 1234567890 on file"
    result_10 = redactor.redact(text_10)
    assert result_10.has_pii is True
    assert result_10.redacted_text == "voter id: <ID_NUMBER> on file"


def test_regex_redact_credit_card():
    redactor = RegexPIIRedactor()
    text_dash = "Charge my card 4532-1234-5678-9012 for the service."
    result_dash = redactor.redact(text_dash)
    assert result_dash.has_pii is True
    assert result_dash.redacted_text == "Charge my card <CREDIT_CARD> for the service."

    text_plain = "Card: 4532123456789012"
    result_plain = redactor.redact(text_plain)
    assert result_plain.has_pii is True
    assert result_plain.redacted_text == "Card: <CREDIT_CARD>"


def test_regex_redact_email_address():
    redactor = RegexPIIRedactor()
    text = "Send my monthly statement to customer.one@finchat.local."
    result = redactor.redact(text)

    assert result.has_pii is True
    assert (
        result.redacted_text
        == "Send my monthly statement to <EMAIL_ADDRESS>."
    )
    assert result.entities[0].entity_type == "EMAIL_ADDRESS"


def test_regex_redact_bangladesh_phone_numbers():
    redactor = RegexPIIRedactor()
    text = "You can call me at +8801712345678 or 01812345678."
    result = redactor.redact(text)

    assert result.has_pii is True
    assert result.redacted_text == "You can call me at <PHONE_NUMBER> or <PHONE_NUMBER>."
    assert len(result.entities) == 2


def test_regex_redact_ip_address():
    redactor = RegexPIIRedactor()
    text = "Suspicious login from IP 192.168.1.50 detected."
    result = redactor.redact(text)

    assert result.has_pii is True
    assert result.redacted_text == "Suspicious login from IP <IP_ADDRESS> detected."


def test_clean_message_without_pii():
    redactor = RegexPIIRedactor()
    text = "What is my account balance? Please deposit 5000 USD."
    result = redactor.redact(text)

    assert result.has_pii is False
    assert result.redacted_text == text
    assert len(result.entities) == 0


def test_multiple_pii_in_single_prompt():
    redactor = RegexPIIRedactor()
    text = (
        "Hello, my NID is 1234567890123, account FC1000000001, "
        "and phone is +8801912345678. Email me at john@example.com."
    )
    result = redactor.redact(text)

    assert result.has_pii is True
    assert result.redacted_text == (
        "Hello, my NID is <ID_NUMBER>, account <ACCOUNT_NUMBER>, "
        "and phone is <PHONE_NUMBER>. Email me at <EMAIL_ADDRESS>."
    )
    assert len(result.entities) == 4


def test_empty_and_whitespace_input():
    redactor = RegexPIIRedactor()
    res_empty = redactor.redact("")
    assert res_empty.has_pii is False
    assert res_empty.redacted_text == ""

    res_none = redactor.redact(None)  # type: ignore[arg-type]
    assert res_none.has_pii is False
    assert res_none.redacted_text == ""


def test_custom_replacement_mapping():
    redactor = RegexPIIRedactor()
    text = "My account is FC1000000001 and NID is 19901234567890123"
    result = redactor.redact(
        text,
        replacements={
            "BANK_ACCOUNT": "[MASKED_ACC]",
            "BD_NID": "[MASKED_NID]",
        },
    )

    assert result.redacted_text == "My account is [MASKED_ACC] and NID is [MASKED_NID]"


def test_convenience_helpers():
    text = "Reach me at 01712345678"
    assert is_pii_present(text) is True
    assert is_pii_present("What is my balance?") is False

    redacted = redact_text(text)
    assert redacted == "Reach me at <PHONE_NUMBER>"
    assert str(redact_pii(text)) == "Reach me at <PHONE_NUMBER>"


def test_presidio_redactor_mocked():
    """Verify PresidioPIIRedactor delegates to AnalyzerEngine and AnonymizerEngine."""
    with patch(
        "security.pii_redactor.PresidioPIIRedactor.__init__", return_value=None
    ):
        presidio_redactor = PresidioPIIRedactor()
        mock_analyzer = MagicMock()
        mock_anonymizer = MagicMock()

        # Mock analyzer results
        mock_res = SimpleNamespace(
            entity_type="BANK_ACCOUNT",
            start=11,
            end=23,
            score=0.95,
        )
        mock_analyzer.analyze.return_value = [mock_res]

        # Mock anonymizer result
        mock_anonymizer.anonymize.return_value = SimpleNamespace(
            text="Account is <ACCOUNT_NUMBER>"
        )

        presidio_redactor._analyzer = mock_analyzer
        presidio_redactor._anonymizer = mock_anonymizer

        result = presidio_redactor.redact("Account is FC1000000001")

        assert result.has_pii is True
        assert result.redacted_text == "Account is <ACCOUNT_NUMBER>"
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == "BANK_ACCOUNT"
        assert result.entities[0].text == "FC1000000001"


def test_get_pii_redactor_fallback_when_presidio_unavailable():
    with patch(
        "security.pii_redactor.PresidioPIIRedactor",
        side_effect=ImportError("No presidio"),
    ):
        set_pii_redactor(None)
        redactor = get_pii_redactor()
        assert isinstance(redactor, RegexPIIRedactor)

