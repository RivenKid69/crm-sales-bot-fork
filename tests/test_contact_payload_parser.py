from src.classifier.extractors.data_extractor import DataExtractor
from src.contact_payload_parser import parse_inline_contact_payload
from src.generator import ResponseGenerator


def test_parse_inline_contact_payload_detects_plain_kz_payment_payload():
    payload = parse_inline_contact_payload("ИИН 123456789012, телефон 87071234567")

    assert payload.iin == "123456789012"
    assert payload.phone == "+77071234567"
    assert payload.kaspi_phone is None
    assert payload.has_payment_payload is True


def test_parse_inline_contact_payload_detects_plus7_payment_payload():
    payload = parse_inline_contact_payload("ИИН 123456789012, телефон +77071234567")

    assert payload.phone == "+77071234567"
    assert payload.has_payment_payload is True


def test_parse_inline_contact_payload_detects_bare_7_payment_payload():
    payload = parse_inline_contact_payload("ИИН 123456789012, телефон 77071234567")

    assert payload.phone == "+77071234567"
    assert payload.kaspi_phone is None
    assert payload.has_payment_payload is True


def test_parse_inline_contact_payload_sets_kaspi_phone_only_with_marker():
    payload = parse_inline_contact_payload("Kaspi 87071234567, ИИН 123456789012")

    assert payload.phone == "+77071234567"
    assert payload.kaspi_phone == "+77071234567"
    assert payload.has_payment_payload is True


def test_parse_inline_contact_payload_email_is_contact_only():
    payload = parse_inline_contact_payload("Почта sales@example.com")

    assert payload.email == "sales@example.com"
    assert payload.has_contact_payload is True
    assert payload.has_payment_payload is False


def test_generator_payment_detector_accepts_plain_8707_number():
    assert ResponseGenerator._client_just_provided_payment_data(
        "ИИН 123456789012, телефон 87071234567"
    ) is True
    assert ResponseGenerator._should_soften_closing_request(
        "contact_provided",
        0,
        "ИИН 123456789012, телефон 87071234567",
    ) is True


def test_generator_payment_detector_accepts_plain_7707_number():
    assert ResponseGenerator._client_just_provided_payment_data(
        "ИИН 123456789012, телефон 77071234567"
    ) is True


def test_data_extractor_uses_shared_parser_for_plain_kz_phone():
    extractor = DataExtractor()

    extracted = extractor.extract(
        "ИИН 123456789012, телефон 87071234567",
        context={"collected_data": {}},
    )

    assert extracted["contact_info"] == "+77071234567"
    assert extracted["contact_type"] == "phone"
    assert extracted["iin"] == "123456789012"
    assert "kaspi_phone" not in extracted


def test_data_extractor_sets_kaspi_phone_only_with_explicit_marker():
    extractor = DataExtractor()

    extracted = extractor.extract(
        "Kaspi 87071234567, ИИН 123456789012",
        context={"collected_data": {}},
    )

    assert extracted["contact_info"] == "+77071234567"
    assert extracted["kaspi_phone"] == "+77071234567"
    assert extracted["iin"] == "123456789012"


def test_data_extractor_uses_shared_parser_for_bare_7_kz_phone():
    extractor = DataExtractor()

    extracted = extractor.extract(
        "ИИН 123456789012, телефон 77071234567",
        context={"collected_data": {}},
    )

    assert extracted["contact_info"] == "+77071234567"
    assert extracted["contact_type"] == "phone"
    assert extracted["iin"] == "123456789012"
    assert "kaspi_phone" not in extracted
