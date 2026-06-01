from jobspy.util import markdown_converter


def test_markdown_converter_preserves_blank_line_before_list_after_heading():
    html = (
        "<strong>OUR HIRING PROCESS:<br/><br/></strong>"
        "<ul><li>We will review your application against our job requirements.</li></ul>"
    )

    markdown = markdown_converter(html)

    assert "**OUR HIRING PROCESS:**" in markdown
    assert (
        "\n\n* We will review your application against our job requirements." in markdown
    )
