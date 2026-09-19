from cryptography.fernet import Fernet

import app.services.credentials as credentials


def test_lzt_token_encryption_is_not_plaintext_and_round_trips(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(credentials, "CREDENTIAL_ENCRYPTION_KEY", key)

    plaintext = "lzt-secret-token-123456"
    ciphertext = credentials._encrypt(plaintext)

    assert plaintext not in ciphertext
    assert credentials._decrypt(ciphertext) == plaintext


def test_missing_encryption_key_fails_closed(monkeypatch):
    monkeypatch.setattr(credentials, "CREDENTIAL_ENCRYPTION_KEY", "")

    try:
        credentials._fernet()
    except RuntimeError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("missing encryption key must fail closed")
