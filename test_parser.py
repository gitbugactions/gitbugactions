import os
import xml.etree.ElementTree as ET

class JUnitXML:
    def __init__(self, folder):
        self.folder = folder

    def get_failed_tests(self):
        failed_tests = []

        for (dirpath, dirnames, filenames) in os.walk(self.folder):
            for filename in filenames:
                if filename.endswith('.xml'):
                    root = ET.parse((os.path.join(dirpath, filename))).getroot()
                    if root.tag == "testsuites":
                        testsuites = root.findall("testsuite")
                    else:
                        testsuites = [root]

                    for testsuite in testsuites:
                        for testcase in testsuite.findall("testcase"):
                            if len(testcase) == 0:
                                continue

                            failure = testcase[0]
                            if failure.tag == "failure":
                                failed_tests.append(
                                    (testcase.attrib['classname'], testcase.attrib['name'], failure.attrib['type'], failure.attrib['message'])
                                )

        return failed_tests