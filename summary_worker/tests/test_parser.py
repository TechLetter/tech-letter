from summary_worker.app.parser import extract_plain_text


def test_extract_plain_text_from_simple_html():

    html = """
    <html>
    <head></head>
    <body>
        <h1>Test</h1>
        <p>This is a test.</p>
    </body>
    </html>
    """

    plain_text = extract_plain_text(html)
    assert plain_text == "Test\nThis is a test."
