from .testparser import TestParser
from junitparser import JUnitXml, TestCase, TestSuite, Error
from typing import List, Union
from pathlib import Path


class JUnitXMLParser(TestParser):

    def __get_failed_tests_xml(self, xml: Union[JUnitXml, TestSuite, TestCase]) -> List[TestCase]:
        """Recursive function to iterate over the JUnit XML file and return a list of failed tests"""
        failed_tests: List[TestCase] = []

        # Check if the element is a TestCase (leaf node)
        if not isinstance(xml, TestCase):
            # If it is a TestSuite, iterate over all elements
            for element in xml:
                if element is not None:
                    failed_tests.extend(self.__get_failed_tests_xml(element))
        else:
            # If it is a TestCase, check if it is failed (not passed, not skipped and
            # without Errors)
            if (not xml.is_passed and not xml.is_skipped and
                        not any(map(lambda r: isinstance(r, Error), xml.result))):
                failed_tests.append(xml)

        return failed_tests


    def _get_failed_tests(self, file: Path) -> list:
        """Returns a list of failed tests from a JUnit XML file"""
        failed_tests: List[TestCase] = []
        
        # Check if it is an xml file
        if file.suffix == '.xml':
            # Load the XML file with the JUnit XML parser
            xml = JUnitXml.fromfile(str(file))
            if xml is not None:
                # Start the recursive function on the root element
                failed_tests.extend(self.__get_failed_tests_xml(xml))

        return failed_tests