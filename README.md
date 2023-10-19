# crawlergpt

## Requirements

It is required to have [act](https://github.com/nektos/act) installed and functional.
To install to Python dependencies run:
```
pip install -r requirements.txt
```

## How to run

Use the `--help` command to obtain the list of options required to run each script.

```
python collect_repos.py
python collect_bugs.py
python export_bugs.py
python filter_bugs.py
```

TBD

## Useful Tricks

### Handling Commits without GitHub Actions

One challenge in collecting bug-fix commit pairs by reproducing GitHub Actions is that GitHub Actions were only released in late 2019.
Moreover, albeit being the most popular as of 2023, its adoption was not immediate.
As a result the majority of commits found on GitHub do not have any associated workflows.

To increase the number of supported commits by GitBug-Actions, it identifies the oldest locally reproducible GitHub Action for each project.
Then, for commits not associated with GitHub Actions, GitBug-Actions uses these as an approximation of the intended configuration.

### Disk Space Management

Build execution has the potential to exhaust available disk space.
To mitigate this, we restrict each build's allocation to a maximum of 3GiB.
However, users are advised to check disk usage frequently and remove dangling docker containers/images in case they occur.

### Concurrent File Access

CI builds may initiate concurrent file access operations, a situation that can escalate to the point of surpassing the user-level open-file limit set by Linux.
This is exarcebated when running multiple builds in parallel.
To overcome this, we recommend setting the open-file limit for your user profile to a higher threshold than the defualt.
