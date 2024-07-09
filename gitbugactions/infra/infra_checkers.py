import os
import yaml
import json
import jsonschema
from abc import ABC, abstractmethod
from pathlib import Path


class InfraChecker(ABC):
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(InfraChecker, cls).__new__(cls)
        return cls.instance

    @abstractmethod
    def check(self, path: Path) -> bool:
        pass


class TerraformChecker(InfraChecker):
    def check(self, path: Path) -> bool:
        return path.match("*.tf")


class PuppetChecker(InfraChecker):
    def check(self, path: Path) -> bool:
        return path.match("*.pp")


class DockerfileChecker(InfraChecker):
    def check(self, path: Path) -> bool:
        return path.match("*Dockerfile") or path.match("Dockerfile*")


class NixChecker(InfraChecker):
    def check(self, path: Path) -> bool:
        return path.match("*.nix")


class PulumiChecker(InfraChecker):
    def check(self, path: Path) -> bool:
        # TODO: we ignore Pulumi because we can't distinguish between Pulumi
        # files and other source code files
        return False


class ChefChecker(InfraChecker):
    def check(self, path: Path) -> bool:
        return ("recipes" in path.parts and path.match("*.rb")) or (
            "cookbooks" in path.parts and path.match("*.rb")
        )


class AnsibleChecker(InfraChecker):
    def __init__(self) -> None:
        # https://github.com/ansible/ansible-lint/tree/main/src/ansiblelint/schemas#schemas-for-ansible-and-its-related-tools
        schemas = (
            Path(os.path.dirname(os.path.abspath(__file__))) / "schemas" / "ansible"
        )
        with open(schemas / "galaxy.json") as f:
            self.galaxy_schema = json.load(f)
        with open(schemas / "inventory.json") as f:
            self.inventory_schema = json.load(f)
        with open(schemas / "meta.json") as f:
            self.meta_schema = json.load(f)
        with open(schemas / "molecule.json") as f:
            self.molecule_schema = json.load(f)
        with open(schemas / "playbook.json") as f:
            self.playbook_schema = json.load(f)
        with open(schemas / "rulebook.json") as f:
            self.rulebook_schema = json.load(f)
        with open(schemas / "tasks.json") as f:
            self.tasks_schema = json.load(f)
        with open(schemas / "vars.json") as f:
            self.vars_schema = json.load(f)

    def check(self, path: Path) -> bool:
        if (
            path.match("*hosts.ini")
            or path.match("*inventory.ini")
            or ("hosts" in path.parts and path.match("*.ini"))
            or ("inventory" in path.parts and path.match("*.ini"))
        ):
            return True

        if not path.match("*.yml") and not path.match("*.yaml"):
            return False

        with open(path) as f:
            yaml_file = yaml.safe_load(f)

        # Galaxy files
        try:
            jsonschema.validate(yaml_file, self.galaxy_schema)
            return True
        except jsonschema.ValidationError:
            pass

        # Inventory files
        try:
            if (
                path.match("*hosts.yaml")
                or path.match("*inventory.yaml")
                or ("hosts" in path.parts and path.match("*.yaml"))
                or ("inventory" in path.parts and path.match("*.yaml"))
                or path.match("*hosts.yml")
                or path.match("*inventory.yml")
                or ("hosts" in path.parts and path.match("*.yml"))
                or ("inventory" in path.parts and path.match("*.yml"))
            ):
                jsonschema.validate(yaml_file, self.inventory_schema)
                return True
        except jsonschema.ValidationError:
            pass

        # Meta files
        try:
            if "meta" in path.parts:
                jsonschema.validate(yaml_file, self.meta_schema)
                return True
        except jsonschema.ValidationError:
            pass

        # Molecule files
        try:
            if "molecule" in path.parts:
                jsonschema.validate(yaml_file, self.molecule_schema)
                return True
        except jsonschema.ValidationError:
            pass

        # Playbook files
        try:
            jsonschema.validate(yaml_file, self.playbook_schema)
            return True
        except jsonschema.ValidationError:
            pass

        # Rulebook files
        try:
            if "rulebooks" in path.parts:
                jsonschema.validate(yaml_file, self.rulebook_schema)
                return True
        except jsonschema.ValidationError:
            pass

        # Tasks files
        try:
            if "tasks" in path.parts or "handlers" in path.parts:
                jsonschema.validate(yaml_file, self.tasks_schema)
                return True
        except jsonschema.ValidationError:
            pass

        # Vars files
        try:
            if (
                "vars" in path.parts
                or "defaults" in path.parts
                or "host_vars" in path.parts
                or "group_vars" in path.parts
            ):
                jsonschema.validate(yaml_file, self.vars_schema)
                return True
        except jsonschema.ValidationError:
            pass

        return False


class KubernetesChecker(InfraChecker):
    def __init__(self) -> None:
        schemas = (
            Path(os.path.dirname(os.path.abspath(__file__))) / "schemas" / "kubernetes"
        )
        with open(schemas / "check.json") as f:
            self.schema = json.load(f)

    def check(self, path: Path) -> bool:
        if not path.match("*.yml") and not path.match("*.yaml"):
            return False

        with open(path) as f:
            yaml_file = yaml.safe_load(f)

        validator = jsonschema.Draft202012Validator(self.schema)
        try:
            validator.validate(yaml_file)
            return True
        except jsonschema.ValidationError:
            pass

        return False


def is_infra_file(path: Path):
    """
    Check if the file is an Infrastructure as Code file

    Args:
        path (Path): Path to the file
    """
    for cls in InfraChecker.__subclasses__():
        if cls().check(path):
            return True
    return False
