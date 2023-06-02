import yaml

from abc import ABC, abstractmethod

class GithubWorkflow(ABC):
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


    @abstractmethod
    def _is_test_keyword(self, name):
        pass


    def has_tests(self):
        """
        Check if the workflow has any tests.

        Returns:
            bool: True if the workflow has tests, False otherwise.
        """
        try:
            # Check if the workflow name contains any test keywords
            if "name" in self.doc and self._is_test_keyword(self.doc["name"]):
                return True
            
            # Check if any job name or step name/run command contains any test keywords
            for job_name, job in self.doc['jobs'].items():
                if self._is_test_keyword(job_name):
                    return True
                
                if 'steps' in job:
                    for step in job['steps']:
                        if 'name' in step and self._is_test_keyword(step['name']):
                            return True
                        
                        if 'run' in step and self._is_test_keyword(step['run']):
                            return True
                    
            return False
        except yaml.YAMLError:
            return False


    def instrument_runs_on(self):
        """
        Instruments the workflow to run only on ubuntu-latest (due to act compatibility).
        """
        def walk_doc(doc):
            """
            Walks the document recursively and replaces any unsupported OS with Ubuntu.
            """
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

        # Replace any unsupported OS with Ubuntu
        for job_name, job in self.doc['jobs'].items():
            if 'runs-on' in job and str(job['runs-on']).lower() in GithubWorkflow.__UNSUPPORTED_OS:
                job['runs-on'] = 'ubuntu-latest'
            if 'strategy' in job and 'os' in job['strategy'] and isinstance(job['strategy']['os'], list):
                job['strategy']['os'] = ['ubuntu-latest']
            if 'strategy' in job:
                walk_doc(job['strategy'])


    def instrument_strategy(self):
        """
        Instruments the workflow to run only one configuration (the fisrt one) per job.
        """
        for job_name, job in self.doc['jobs'].items():
            if 'strategy' in job and 'matrix' in job['strategy']:
                for key, value in job['strategy']['matrix'].items():
                    if isinstance(value, list):
                        job['strategy']['matrix'][key] = [value[0]]


    @abstractmethod
    def instrument_test_steps(self):
        """
        Instruments the test steps to generate reports.
        """
        pass

    def save_yaml(self, new_path):
        with open(new_path, 'w') as file:
            yaml.dump(self.doc, file)