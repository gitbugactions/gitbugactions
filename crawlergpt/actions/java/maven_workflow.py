from crawlergpt.actions.workflow import GitHubWorkflow

class MavenWorkflow(GitHubWorkflow):
    # Correspond to the maven lifecycle phases that run tests
    # https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html#Lifecycle_Reference
    __TESTS_KEYWORDS = ["test", "package", "integration-test", "verify", "install"]
    
    def _is_test_keyword(self, name):
        return any(map(lambda word: word.lower() in MavenWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    def instrument_test_steps(self):
        pass