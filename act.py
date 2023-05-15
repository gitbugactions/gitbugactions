import os
import xml.etree.ElementTree as ET
import subprocess

class JUnitXML:
    def __init__(self, folder):
        self.folder = folder

    def parse(self):
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
                                print(testcase.attrib['classname'], failure.attrib['type'], failure.attrib['message'])

class Act:
    __ACT_PATH="act"
    __FLAGS="--bind --rm"
    __DEFAULT_RUNNERS = "-P ubuntu-latest=catthehacker/ubuntu:full-latest" + \
        " -P ubuntu-22.04=catthehacker/ubuntu:act-22.04" + \
        " -P ubuntu-20.04=catthehacker/ubuntu:full-20.04" + \
        " -P ubuntu-18.04=catthehacker/ubuntu:full-18.04"

    def run_act(self, repo_path, workflows):
        command = f"cd {repo_path} &&"
        command += f"{Act.__ACT_PATH} {Act.__DEFAULT_RUNNERS} {Act.__FLAGS}"

        for workflow in workflows:
            p = subprocess.Popen(command + f" -W {workflow}", shell=True)
            code = p.wait()
            JUnitXML(os.path.join(repo_path, "target", "surefire-reports")).parse()
            #JUnitXML(os.path.join(repo_path, "target" , "surefire-reports")).parse()


act = Act()

# Needs to filter the workflows with tests
# Needs to filter OS because act only runs in ubuntu
act.run_act("/home/nfsaavedra/Downloads/flacoco", [".github/workflows/tests.yml"])
#https://github.com/marketplace/actions/publish-test-results#generating-test-result-files