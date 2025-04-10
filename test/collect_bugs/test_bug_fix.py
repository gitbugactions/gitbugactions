from unittest.mock import Mock

from collect_bugs import PatchCollector


def test_is_bug_fix():
    repo = Mock()
    repo.language.return_value = "java"
    collector = PatchCollector(repo)

    commit = Mock()
    commit.message = "fixing bug"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "bug"
    assert not collector._PatchCollector__is_bug_fix(commit)
    commit.message = "resolve issue"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "apply patch"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Repair issue"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "correct issue"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Workaround issue"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Test test. Fixes bug"
    assert collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Test test. Prefix"
    assert not collector._PatchCollector__is_bug_fix(commit)
    commit.message = "Test test. Small fix"
    assert collector._PatchCollector__is_bug_fix(commit)
