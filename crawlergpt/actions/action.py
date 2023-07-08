import logging
import re
import shutil
import os
import pygit2


class Action:
    # Class to represent a GitHub Action
    # Note: We consider only the major version of the action, thus we ignore the minor and patch versions

    def __init__(self, declaration: str):
        self.declaration = declaration
        self.name = self.__get_name()
        if self.is_semantic_version():
            self.version = self.__get_semantic_version()
        else:
            self.version = self.__get_version()

    def is_semantic_version(self) -> bool:
        return (
            re.match(
                r"^[a-zA-Z0-9\-_\/]+@v[0-9]+(\.[0-9]+)?(\.[0-9]+)?", self.declaration
            )
            is not None
        )

    def __get_name(self) -> str:
        return self.declaration.split("@")[0].strip()

    def __get_semantic_version(self) -> str:
        return self.declaration.split("@")[1].split(".")[0].strip()

    def __get_version(self) -> str:
        return self.declaration.split("@")[1].strip()

    def download(self, action_dir: str):
        """
        Download the action to the action dir
        """
        logging.info(f"Downloading action {self.name}@{self.version} to {action_dir}")
        if not self.is_semantic_version():
            raise Exception(
                f"Non-semantic version not supported: {self.name}@{self.version}"
            )

        # If the action is already in the cache, raise an exception
        if os.path.exists(action_dir):
            logging.warning(f"Action directory already exists: {action_dir}")
            return

        try:
            # Clone the action to the action dir using pygit2
            repo = pygit2.clone_repository(
                f"https://github.com/{self.name}.git", action_dir
            )

            # Checkout the action version
            repo.checkout(f"refs/tags/{self.version}")

            # Remove gitignore so that act doesn't have to
            gitignore_path = os.path.join(action_dir, ".gitignore")
            if os.path.exists(gitignore_path):
                os.remove(gitignore_path)
        except Exception:
            # If something goes wrong, delete the action dir
            shutil.rmtree(action_dir, ignore_errors=True)
            raise Exception(
                f"Error while downloading action {self.name}@{self.version}: {traceback.format_exc()}"
            )

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def __eq__(self, other):
        return self.name == other.name and self.version == other.version
