# crawlergpt

## Requirements

It is required to have [act](https://github.com/nektos/act) installed and functional.
To install to Python dependencies run:
```
pip install -r requirements.txt
```


## Useful Tricks

### Handling Commits without GitHub Actions

One challenge in collecting bug-fix commit pairs by reproducing GitHub Actions is that GitHub Actions were only released in late 2019.
Moreover, albeit being the most popular as of 2023, its adoption was not immediate.
As a result the majority of commits found on GitHub do not have any associated workflows.

To increase the number of supported commits by GitBug-Actions, it identifies the oldest locally reproducible GitHub Action for each project.
Then, for commits not associated with GitHub Actions, GitBug-Actions uses these as an approximation of the intended configuration.
