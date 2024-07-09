from gitbugactions.infra.infra_checkers import *


def test_infra_terraform_checker():
    checker = TerraformChecker()
    assert checker.check(Path("test/resources/test_infra/test.tf"))


def test_infra_terraform_checker_false():
    checker = TerraformChecker()
    assert not checker.check(Path("test/resources/test_infra/test.txt"))


def test_infra_puppet_checker():
    checker = PuppetChecker()
    assert checker.check(Path("test/resources/test_infra/test.pp"))


def test_infra_puppet_checker_false():
    checker = PuppetChecker()
    assert not checker.check(Path("test/resources/test_infra/test.txt"))


def test_infra_docker_checker():
    checker = DockerfileChecker()
    assert checker.check(Path("test/resources/test_infra/Dockerfile"))
    assert checker.check(Path("test/resources/test_infra/Dockerfile.test"))
    assert checker.check(Path("test/resources/test_infra/test.Dockerfile"))


def test_infra_docker_checker_false():
    checker = DockerfileChecker()
    assert not checker.check(Path("test/resources/test_infra/test.txt"))


def test_infra_nix_checker():
    checker = NixChecker()
    assert checker.check(Path("test/resources/test_infra/test.nix"))


def test_infra_nix_checker_false():
    checker = NixChecker()
    assert not checker.check(Path("test/resources/test_infra/test.txt"))


def test_infra_chef_checker():
    checker = ChefChecker()
    assert checker.check(Path("test/resources/test_infra/recipes/test.rb"))


def test_infra_chef_checker_false():
    checker = ChefChecker()
    assert not checker.check(Path("test/resources/test_infra/test.rb"))


def test_infra_ansible_checker():
    checker = AnsibleChecker()
    assert checker.check(Path("test/resources/test_infra/ansible/playbook.yml"))
    assert checker.check(Path("test/resources/test_infra/ansible/hosts.yml"))
    assert checker.check(Path("test/resources/test_infra/ansible/inventory.ini"))
    assert checker.check(Path("test/resources/test_infra/ansible/tasks/tasks.yml"))
    assert checker.check(Path("test/resources/test_infra/ansible/vars/vars.yml"))
    assert checker.check(Path("test/resources/test_infra/ansible/galaxy.yml"))
    assert checker.check(
        Path("test/resources/test_infra/ansible/rulebooks/rulebook.yml")
    )
    assert checker.check(
        Path("test/resources/test_infra/ansible/molecule/molecule.yml")
    )


def test_infra_ansible_checker_false():
    checker = AnsibleChecker()
    assert not checker.check(Path("test/resources/test_infra/test.txt"))
    assert not checker.check(Path("test/resources/test_infra/ansible/tasks.yml"))
    assert not checker.check(Path("test/resources/test_infra/test.yml"))


def test_infra_kubernetes_checker():
    checker = KubernetesChecker()
    assert checker.check(Path("test/resources/test_infra/kubernetes/deployment.yaml"))
    # (Path("test/resources/test_infra/kubernetes/replicate_set.yaml"))


def test_infra_kubernetes_checker_false():
    checker = KubernetesChecker()
    assert not checker.check(Path("test/resources/test_infra/test.yml"))
    assert not checker.check(Path("test/resources/test_infra/ansible/tasks.yml"))


def test_infra_is_infra():
    assert is_infra_file(Path("test/resources/test_infra/kubernetes/deployment.yaml"))
    assert is_infra_file(Path("test/resources/test_infra/ansible/tasks/tasks.yml"))
    assert is_infra_file(Path("test/resources/test_infra/ansible/hosts.ini"))
    assert is_infra_file(Path("test/resources/test_infra/ansible/inventory.ini"))
    assert is_infra_file(Path("test/resources/test_infra/ansible/playbook.yml"))
    assert is_infra_file(Path("test/resources/test_infra/test.nix"))


def test_infra_is_infra_false():
    assert not is_infra_file(Path("test/resources/test_infra/test.txt"))
    assert not is_infra_file(Path("test/resources/test_infra/test.yml"))
