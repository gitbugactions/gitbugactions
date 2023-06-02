import yaml

class GithubWorkflow:
    # FIXME change keywords specific to languages
    __TESTS_KEYWORDS = ["test", "tests", "testing", "verify"]
    __UNSUPPORTED_OS = [
        "windows-latest",
        "windows-2022",
        "windows-2019",
        "windows-2016",
        "macos-13",
        "macos-13-xl",
        "macos-latest",
        "macos-12",
        "macos-latest-xl",
        "macos-12-xl",
        "macos-11",
        "ubuntu-22.04",
        "ubuntu-20.04",
        "ubuntu-18.04"
    ]

    def __init__(self, path):
        with open(path, "r") as stream:
            self.doc = yaml.safe_load(stream)
            self.path = path

            # Solves problem where pyyaml parses 'on' (used in Github actions) as True
            if True in self.doc:
                self.doc['on'] = self.doc[True]
                self.doc.pop(True)

    def __is_test(self, name):
        return any(map(lambda word: word.lower() in GithubWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    # FIXME remove integration tests
    def has_tests(self):
        '''
        Check if the workflow has any tests.

        Returns:
            bool: True if the workflow has tests, False otherwise.
        '''
        try:
            # Check if the workflow name contains any test keywords
            if "name" in self.doc and self.__is_test(self.doc["name"]):
                return True
            
            # Check if any job name or step name/run command contains any test keywords
            for job_name, job in self.doc['jobs'].items():
                if self.__is_test(job_name):
                    return True
                
                if 'steps' in job:
                    for step in job['steps']:
                        if 'name' in step and self.__is_test(step['name']):
                            return True
                        
                        if 'run' in step and self.__is_test(step['run']):
                            return True
                    
            return False
        except yaml.YAMLError:
            return False
            
    def remove_unsupported_os(self):
        def walk_doc(doc):
            if isinstance(doc, dict):
                for key, value in doc.items():
                    if str(value).lower() in GithubWorkflow.__UNSUPPORTED_OS:
                        doc[key] = "ubuntu-latest"
                    else:
                        walk_doc(value)
            elif isinstance(doc, list):
                doc[:] = filter(lambda x: str(x).lower() not in GithubWorkflow.__UNSUPPORTED_OS, doc)
                for value in doc:
                    walk_doc(value)
                if len(doc) == 0:
                    doc.append('ubuntu-latest')

        for job_name, job in self.doc['jobs'].items():
            if 'runs-on' in job and str(job['runs-on']).lower() in GithubWorkflow.__UNSUPPORTED_OS:
                job['runs-on'] = 'ubuntu-latest'
            if 'strategy' in job and 'os' in job['strategy'] and isinstance(job['strategy']['os'], list):
                job['strategy']['os'] = ['ubuntu-latest']
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


    def instrument_test_actions(self):
        '''
        Instrument the workflow to generate xml reports during test execution
        '''
        for job_name, job in self.doc['jobs'].items():
            if 'steps' in job:
                for step in job['steps']:
                    if 'run' in step and self.__is_test(step['run']):
                        # TODO: only supports python for now
                        if "pytest" in step['run']:
                            step['run'] = step['run'].replace("pytest", "pytest --junitxml=report.xml")


    def save_yaml(self, new_path):
        with open(new_path, 'w') as file:
            yaml.dump(self.doc, file)