from junitparser import TestCase
from junitparser.junitparser import Failure, Error
from filter_bugs import equal_test_results


def test_check_same_results():
    old_results = [
        {"classname": "test", "name": "test", "results": [{"result": "Passed"}]}
    ]
    new_results = [TestCase("test", classname="test")]
    assert equal_test_results(old_results, new_results)

    old_results.append(
        {"classname": "test", "name": "test2", "results": [{"result": "Failure"}]}
    )
    test_case = TestCase("test2", classname="test")
    test_case.result = [Failure()]
    new_results.append(test_case)
    assert equal_test_results(old_results, new_results)

    old_results.append(
        {
            "classname": "test",
            "name": "test3",
            "results": [{"result": "Failure"}, {"result": "Error"}],
        }
    )
    test_case = TestCase("test3", classname="test")
    test_case.result = [Error(), Failure()]
    new_results.append(test_case)
    assert equal_test_results(old_results, new_results)


def test_check_different_results():
    old_results = [
        {"classname": "test", "name": "test", "results": [{"result": "Passed"}]}
    ]
    test_case = TestCase("test", classname="test")
    test_case.result = [Failure()]
    new_results = [test_case]
    assert not equal_test_results(old_results, new_results)

    old_results = [
        {"classname": "test", "name": "test", "results": [{"result": "Failure"}]}
    ]
    new_results = [TestCase("test", classname="test")]
    assert not equal_test_results(old_results, new_results)

    old_results = [
        {"classname": "test", "name": "test", "results": [{"result": "Failure"}]}
    ]
    test_case = TestCase("test", classname="test")
    test_case.result = [Failure(), Failure()]
    new_results = [test_case]
    assert not equal_test_results(old_results, new_results)

    old_results = [
        {"classname": "test", "name": "test2", "results": [{"result": "Failure"}]}
    ]
    test_case = TestCase("test", classname="test")
    test_case.result = [Failure()]
    new_results = [test_case]
    assert not equal_test_results(old_results, new_results)

    old_results = [
        {"classname": "test", "name": "test", "results": [{"result": "Failure"}]}
    ]
    test_case = TestCase("test", classname="test2")
    test_case.result = [Failure()]
    new_results = [test_case]
    assert not equal_test_results(old_results, new_results)
