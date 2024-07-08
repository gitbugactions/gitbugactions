from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.actions import ActTestsRun
from junitparser import Error
import pytest


def parse_junitxml(file):
    """Parse a test report file with the JUnitXMLParser."""
    parser = JUnitXMLParser()
    tests = parser.get_test_results(file)
    failing_tests = list(
        filter(
            lambda test: (
                not test.is_passed
                and not test.is_skipped
                and not any(map(lambda r: isinstance(r, Error), test.result))
            ),
            tests,
        )
    )
    return tests, failing_tests


@pytest.mark.parametrize(
    "xml_file, nr_tests, nr_of_failing_tests",
    [
        ("test/resources/test_reports/java/maven_flacoco_passing.xml", 7, 0),
        ("test/resources/test_reports/java/maven_flacoco_failing.xml", 7, 3),
        ("test/resources/test_reports/java/maven_flacoco_error.xml", 30, 0),
        ("test/resources/test_reports/java/", 44, 3),
    ],
)
def test_maven(xml_file, nr_tests, nr_of_failing_tests):
    """Test the JUnitXMLParser on Maven test reports."""
    tests, failing_tests = parse_junitxml(xml_file)
    assert len(failing_tests) == nr_of_failing_tests
    assert len(tests) == nr_tests


@pytest.mark.parametrize(
    "xml_file, nr_tests, nr_of_failing_tests",
    [
        ("test/resources/test_reports/python/pytest_gitbugactions_passing.xml", 3, 0),
        ("test/resources/test_reports/python/pytest_gitbugactions_failing.xml", 2, 1),
        ("test/resources/test_reports/python/", 5, 1),
    ],
)
def test_pytest(xml_file, nr_tests, nr_of_failing_tests):
    """Test the JUnitXMLParser on pytest test reports."""
    tests, failing_tests = parse_junitxml(xml_file)
    assert len(failing_tests) == nr_of_failing_tests
    assert len(tests) == nr_tests


@pytest.mark.parametrize(
    "xml_file, nr_tests, nr_of_failing_tests",
    [
        ("test/resources/test_reports/java/maven_flacoco_passing.xml", 7, 0),
        ("test/resources/test_reports/java/maven_flacoco_failing.xml", 7, 3),
        ("test/resources/test_reports/java/maven_flacoco_error.xml", 30, 0),
        ("test/resources/test_reports/java/", 44, 3),
    ],
)
def test_act_tests_run(xml_file, nr_tests, nr_of_failing_tests):
    tests, _ = parse_junitxml(xml_file)
    tests_run = ActTestsRun(True, tests, "", "", "", "", "", 0, False, 0)
    assert len(tests_run.failed_tests) == nr_of_failing_tests
    assert len(tests_run.tests) == nr_tests
