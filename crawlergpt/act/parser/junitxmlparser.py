from testparser import TestParser
from junitparser import JUnitXml, TestCase, TestSuite
from typing import List, Union


class JUnitXMLParser(TestParser):

    def __get_failed_tests(self, xml: Union[JUnitXml, TestSuite, TestCase]) -> List[TestCase]:
        """Recursive function to iterate over the JUnit XML file and return a list of failed tests"""
        failed_tests: List[TestCase] = []

        # Check if the element is a TestCase (leaf node)
        if not isinstance(xml, TestCase):
            # If it is a TestSuite, iterate over all elements
            for element in xml:
                if element != None:
                    failed_tests.extend(self.__get_failed_tests(element))
        else:
            # If it is a TestCase, check if it is failed (not passed and not skipped)
            if not xml.is_passed and not xml.is_skipped:
                failed_tests.append(xml)

        return failed_tests

    def get_failed_tests(self, file: str) -> List[TestCase]:
        """Returns a list of failed tests from a JUnit XML file"""
        failed_tests: List[TestCase] = []
        
        # Check if it is an xml file
        if file.endswith('.xml'):
            # Load the XML file with the JUnit XML parser
            xml = JUnitXml.fromfile(file)
            if xml != None:
                # Start the recursive function on the root element
                failed_tests.extend(self.__get_failed_tests(xml))

        return failed_tests