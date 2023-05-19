import os
import yaml
import subprocess
import xml.etree.ElementTree as ET

class GithubWorkflow:
    __TESTS_KEYWORDS = ["test", "tests", "testing"]
    __UNSUPPORTED_OS = [
        "windows-latest",
        "windows-2022",
        "windows-2019",
        "macos-13",
        "macos-13-xl",
        "macos-latest",
        "macos-12",
        "macos-latest-xl",
        "macos-12-xl",
        "macos-11"
    ]

    def __init__(self, path):
        with open(path, "r") as stream:
            self.doc = yaml.safe_load(stream)

            # Solves problem where pyyaml parses 'on' (used in Github actions) as True
            if True in self.doc:
                self.doc['on'] = self.doc[True]
                self.doc.pop(True)

    def __is_test(self, name):
        return any(map(lambda word: word.lower() in GithubWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    def has_tests(self):
        try:
            if self.__is_test(self.doc["name"]):
                return True
            
            for job_name, job in self.doc['jobs'].items():
                if self.__is_test(job_name):
                    return True
                
                for step in job['steps']:
                    if 'name' in step and self.__is_test(step['name']):
                        return True
                    
            return False
        except yaml.YAMLError:
            return False
            
    def remove_unsupported_os(self):
        def walk_doc(doc):
            if isinstance(doc, dict):
                for key, value in doc.items():
                    if value in GithubWorkflow.__UNSUPPORTED_OS:
                        doc[key] = "ubuntu-latest"
                    else:
                        walk_doc(value)
            elif isinstance(doc, list):
                doc[:] = filter(lambda x: x not in GithubWorkflow.__UNSUPPORTED_OS, doc)
                for value in doc:
                    walk_doc(value)

        for job_name, job in self.doc['jobs'].items():
            if 'runs-on' in job and job['runs-on'] in GithubWorkflow.__UNSUPPORTED_OS:
                job['runs-on'] = 'ubuntu-latest'
            if 'strategy' in job:
                walk_doc(job['strategy'])

    def simplify_strategies(self):
        '''
        Keep only first elements from lists
        '''
        for job_name, job in self.doc['jobs'].items():
            if 'strategy' in job and 'matrix' in job['strategy']:
                for key, value in job['strategy']['matrix'].items():
                    if isinstance(value, list):
                        job['strategy']['matrix'][key] = [value[0]] 

    def save_yaml(self, new_path):
        with open(new_path, 'w') as file:
            yaml.dump(self.doc, file)


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
                                    (testcase.attrib['classname'], failure.attrib['type'], failure.attrib['message'])
                                )

        return failed_tests


class Act:
    __ACT_PATH="act"
    # The flag -u allows files to be created with the current user
    __FLAGS=f"--bind --rm --container-options '-u {os.getuid()}'"
    __DEFAULT_RUNNERS = "-P ubuntu-latest=catthehacker/ubuntu:full-latest" + \
        " -P ubuntu-22.04=catthehacker/ubuntu:act-22.04" + \
        " -P ubuntu-20.04=catthehacker/ubuntu:full-20.04" + \
        " -P ubuntu-18.04=catthehacker/ubuntu:full-18.04"

    def run_act(self, repo_path, workflows, test_parser):
        command = f"cd {repo_path} && "
        command += f"{Act.__ACT_PATH} {Act.__DEFAULT_RUNNERS} {Act.__FLAGS}"

        for workflow in workflows:
            p = subprocess.Popen(command + f" -W {workflow}", shell=True)
            code = p.wait()

        return test_parser.get_failed_tests()


def get_failed_tests(repo_path):
    act = Act()
    workflows_path = os.path.join(repo_path, ".github", "workflows")
    tests_workflows = []

    for (dirpath, dirnames, filenames) in os.walk(workflows_path):
        yaml_files = list(filter(lambda file: file.endswith('.yml') or file.endswith('.yaml'), filenames))
        for file in yaml_files:
            workflow = GithubWorkflow(os.path.join(dirpath, file))
            if not workflow.has_tests():
                continue

            workflow.remove_unsupported_os()
            workflow.simplify_strategies()
            new_filename = file.split('.')[0] + "-crawler." + file.split('.')[1]
            new_path = os.path.join(dirpath, new_filename)
            workflow.save_yaml(new_path)
            tests_workflows.append(os.path.relpath(new_path, repo_path))

    parser = JUnitXML(os.path.join(repo_path, "target", "surefire-reports"))
    failed_tests = act.run_act(repo_path, tests_workflows, parser)

    for test_workflow in tests_workflows:
       os.remove(os.path.join(repo_path, test_workflow))

    return failed_tests


#repo_path = "/home/nfsaavedra/Downloads/flacoco"
#print(get_failed_tests(repo_path))
#https://github.com/marketplace/actions/publish-test-results#generating-test-result-files