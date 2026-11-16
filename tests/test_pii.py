from hospitality_elt.pii import PiiPolicy, apply_policy, pseudonymise
from hospitality_elt.sources.workforce import WorkforceApiSource

KEY = "test-key"


def test_employee_record_is_stripped_of_identity_contact_bank_and_pay():
    record = {
        "employee_id": "EMP0001",
        "first_name": "Alex",
        "last_name": "Lee",
        "email": "alex@example.com",
        "mobile": "0400000000",
        "date_of_birth": "1990-01-01",
        "tax_file_number": "123",
        "bank_bsb": "000-000",
        "bank_account_number": "1",
        "home_address": {"street": "1 Rd"},
        "pay_rate": "30.00",
        "display_name": "Alex L.",
        "role": "chef",
        "employment_type": "casual",
        "home_location_id": "1001",
        "status": "active",
        "manager_id": "EMP0002",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    policy = WorkforceApiSource.entities["employees"].pii
    clean, removed = apply_policy(record, policy, KEY)

    assert set(clean) == {
        "employee_id",
        "role",
        "employment_type",
        "home_location_id",
        "status",
        "manager_id",
        "updated_at",
    }
    assert clean["employee_id"] == pseudonymise("EMP0001", KEY)
    assert clean["employee_id"] != "EMP0001"
    assert {"email", "tax_file_number", "bank_account_number", "pay_rate"} <= removed


def test_pseudonym_is_stable_so_cross_system_joins_work():
    assert pseudonymise("EMP0001", KEY) == pseudonymise("EMP0001", KEY)
    assert pseudonymise("EMP0001", KEY) != pseudonymise("EMP0001", "other-key")


def test_denylist_catches_unexpected_nested_fields():
    record = {"id": 1, "details": {"customer_email": "x@y.z", "items": [{"card_number": "4"}]}}
    clean, removed = apply_policy(record, PiiPolicy(), KEY)
    assert clean == {"id": 1, "details": {"items": [{}]}}
    assert "details.customer_email" in removed


def test_allow_list_keeps_business_fields():
    clean, _ = apply_policy({"address": "1 Venue St"}, PiiPolicy(allow=frozenset({"address"})), KEY)
    assert clean == {"address": "1 Venue St"}
