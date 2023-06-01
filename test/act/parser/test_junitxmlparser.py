from crawlergpt.act.parser.junitxmlparser import JUnitXMLParser

def parse_junitxml(file):
    """Parse a test report file with the JUnitXMLParser."""
    parser = JUnitXMLParser()
    failing_tests = parser.get_failed_tests(file)
    return failing_tests


def test_flacoco_passing():
    """Test the JUnitXMLParser with a passing test report."""
    failing_tests = parse_junitxml("test/act/parser/testdata/flacoco_passing.xml")
    assert len(failing_tests) == 0
    
def test_flacoco_failing():
    """Test the JUnitXMLParser with a failing test report."""
    failing_tests = parse_junitxml("test/act/parser/testdata/flacoco_failing.xml")
    assert len(failing_tests) == 1