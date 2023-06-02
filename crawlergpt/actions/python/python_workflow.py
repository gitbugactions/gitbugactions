from crawlergpt.actions.workflow import GithubWorkflow

class PytestWorkflow(GithubWorkflow): 
    __TESTS_KEYWORDS = ["pytest"]
    
    def _is_test_keyword(self, name):
        return any(map(lambda word: word.lower() in PytestWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    def instrument_test_steps(self):
        for job_name, job in self.doc['jobs'].items():
            if 'steps' in job:
                for step in job['steps']:
                    if 'run' in step and self._is_test_keyword(step['run']):
                        if "pytest" in step['run']:
                            step['run'] = step['run'].replace("pytest", "pytest --junitxml=report.xml")
