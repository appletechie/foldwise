from foldwise import sensitive

KEY = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2"


def test_detects_real_keys():
    assert sensitive.is_sensitive(f'"apiKey": "{KEY}"')
    assert sensitive.is_sensitive("api-key: EJjtE7Hk2mQpL9xZ4vN8wR3tY6uB1cD5fG0hJ2kM")
    assert sensitive.is_sensitive("-----BEGIN OPENSSH PRIVATE KEY-----\nabc")
    assert sensitive.is_sensitive("id,secret\napi_j9fDhQjaQmGXSkcGy8t3qjqF,S1Dyskk9SwwDqqwJ9i4Dc3aE")
    assert sensitive.is_sensitive("Mercury backup codes\n1234-5678")


def test_ignores_placeholders_and_prose():
    assert not sensitive.is_sensitive("set api_key = <your-key-here>")
    assert not sensitive.is_sensitive("The API key goes in the settings page.")
    assert not sensitive.is_sensitive("password: hunter2")
    assert not sensitive.is_sensitive("Our secret: great service")


def test_mask_hides_the_value_and_is_not_detected_again():
    text = f"token={KEY} and more"
    masked = sensitive.mask(text)
    assert KEY not in masked
    assert "[masked]" in masked
    assert masked.endswith(" and more")
    assert not sensitive.is_sensitive(masked.replace("[masked]", ""))
