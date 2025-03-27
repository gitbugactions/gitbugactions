from gitbugactions.actions.templates.languages.cmake.cmake import CMakeTemplate


class CTemplate(CMakeTemplate):
    """C language template for GitHub Actions workflow"""

    @classmethod
    def get_name(cls) -> str:
        return "c"
