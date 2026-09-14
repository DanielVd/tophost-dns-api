from tophost_api.client.session import TophostHTTPSession


def test_cookie_roundtrip():
    source = TophostHTTPSession()

    source.session.cookies.set(
        "example",
        "secret",
        domain=".tophost.it",
        path="/",
    )

    exported = source.export_cookies()

    target = TophostHTTPSession()
    target.import_cookies(exported)

    assert target.session.cookies.get(
        "example",
        domain=".tophost.it",
        path="/",
    ) == "secret"
