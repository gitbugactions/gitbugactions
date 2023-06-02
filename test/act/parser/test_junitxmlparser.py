from crawlergpt.actions.parser.junitxml_parser import JUnitXMLParser

import pytest

def parse_junitxml(file):
    """Parse a test report file with the JUnitXMLParser."""
    parser = JUnitXMLParser()
    failing_tests = parser.get_failed_tests(file)
    return failing_tests


@pytest.mark.parametrize("xml_file, nr_of_failing_tests", [
    ("test/resources/test_reports/java/flacoco_passing.xml", 0),
    ("test/resources/test_reports/java/flacoco_failing.xml", 3),
    ("test/resources/test_reports/java/", 3),
])
def test_maven(xml_file, nr_of_failing_tests):
    """Test the JUnitXMLParser on Maven test reports."""
    failing_tests = parse_junitxml(xml_file)
    assert len(failing_tests) == nr_of_failing_tests
    
@pytest.mark.parametrize("xml_file, nr_of_failing_tests", [
    ("test/resources/test_reports/python/crawlergpt_passing.xml", 0),
    ("test/resources/test_reports/python/crawlergpt_failing.xml", 1),
    ("test/resources/test_reports/python/", 1),
])
def test_pytest(xml_file, nr_of_failing_tests):
    """Test the JUnitXMLParser on pytest test reports."""
    failing_tests = parse_junitxml(xml_file)
    assert len(failing_tests) == nr_of_failing_tests