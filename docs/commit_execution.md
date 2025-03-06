### Executing Tests with Patches Applied

```python
from unidiff import PatchSet
from gitbugactions.commit_execution import CommitExecutor

# Initialize the executor
executor = CommitExecutor(
    repo_url="https://github.com/org/repo.git",
    memory_limit="7g",
    timeout=600
)

try:
    # Load patches
    with open("test_changes.patch", "r") as f:
        test_patch = PatchSet(f.read())
    
    with open("non_code_changes.patch", "r") as f:
        non_code_patch = PatchSet(f.read())
    
    # Execute tests at a commit with patches applied
    result = executor.execute_at_commit_with_patches(
        commit_sha="def456",
        patches=[test_patch, non_code_patch]
    )
    
    # Check which patches were successfully applied
    print(f"Patches applied: {result.patches_applied}")
    
    # Check test results
    print(f"Passed tests: {len(result.passed_tests)}")
    print(f"Failed tests: {len(result.failed_tests)}")
    print(f"Skipped tests: {len(result.skipped_tests)}")
    print(f"Error tests: {len(result.error_tests)}")
finally:
    # Clean up resources
    executor.cleanup()
```

##### execute_at_commit_with_patches

```python
def execute_at_commit_with_patches(
    self,
    commit_sha: str,
    patches: Optional[List[Union[PatchSet, str]]] = None,
    workflow_paths: Optional[List[str]] = None,
) -> CommitExecutionResult
```

Executes tests at a commit after applying specified patches.

- `commit_sha`: SHA of the commit to execute tests at
- `patches`: Optional list of patches to apply
- `workflow_paths`: Optional list of specific workflow paths to execute

Returns a `CommitExecutionResult` containing the results of the execution. 