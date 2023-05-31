import os
from junitparser import JUnitXml, TestCase

class TestParser:
    def __init__(self, folder):
        self.folder = folder


    def _get_failed_tests(self, xml):
        failed_tests = []

        if not isinstance(xml, TestCase):
            for element in xml:
                failed_tests.extend(self._get_failed_tests(element))
        else:
            if not xml.is_passed and not xml.is_skipped:
                failed_tests.append(xml)

        return failed_tests


    def get_failed_tests(self):
        failed_tests = []

        for (dirpath, _, filenames) in os.walk(self.folder):
            for filename in filenames:
                if filename.endswith('.xml'):
                    xml = JUnitXml.fromfile(os.path.join(dirpath, filename))
                    failed_tests.extend(self._get_failed_tests(xml))

        return failed_tests