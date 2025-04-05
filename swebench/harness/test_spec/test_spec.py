import hashlib
import json
import platform

from dataclasses import dataclass
from typing import Any, Union, cast

from swebench.harness.constants import (
    DEFAULT_DOCKER_SPECS,
    KEY_INSTANCE_ID,
    LATEST,
    MAP_REPO_TO_EXT,
    MAP_REPO_VERSION_TO_SPECS,
    USE_X86,
    SWEbenchInstance,
)
from swebench.harness.dockerfiles import (
    get_dockerfile_base,
    get_dockerfile_env,
    get_dockerfile_instance,
)
from swebench.harness.test_spec.create_scripts import (
    make_repo_script_list,
    make_env_script_list,
    make_eval_script_list,
)


@dataclass
class TestSpec:
    """
    A dataclass that represents a test specification for a single instance of SWE-bench.
    """

    instance_id: str
    repo: str
    version: str
    repo_script_list: list[str]
    eval_script_list: list[str]
    env_script_list: list[str]
    arch: str
    FAIL_TO_PASS: list[str]
    PASS_TO_PASS: list[str]
    language: str
    docker_specs: dict
    namespace: str
    base_image_tag: str = LATEST
    env_image_tag: str = LATEST
    instance_image_tag: str = LATEST
    copy_repo_from_host_path: str = None

    @property
    def setup_env_script(self):
        return (
            "\n".join(["#!/bin/bash", "set -euxo pipefail"] + self.env_script_list)
            + "\n"
        )

    @property
    def eval_script(self):
        return (
            "\n".join(["#!/bin/bash", "set -uxo pipefail"] + self.eval_script_list)
            + "\n"
        )
        # Don't exit early because we need to revert tests at the end

    @property
    def install_repo_script(self):
        return (
            "\n".join(["#!/bin/bash", "set -euxo pipefail"] + self.repo_script_list)
            + "\n"
        )

    @property
    def base_image_key(self):
        return (
            f"sweb.base.{MAP_REPO_TO_EXT[self.repo]}.{self.arch}:{self.base_image_tag}"
        )

    @property
    def env_image_key(self):
        """
        The key for the environment image is based on the hash of the environment script list.
        If the environment script list changes, the image will be rebuilt automatically.

        Note that old images are not automatically deleted, so consider cleaning up old images periodically.
        """
        hash_key = str(self.env_script_list)
        if self.docker_specs != {}:
            hash_key += str(self.docker_specs)
        hash_object = hashlib.sha256()
        hash_object.update(hash_key.encode("utf-8"))
        hash_value = hash_object.hexdigest()
        val = hash_value[:22]  # 22 characters is still very likely to be unique
        return f"sweb.env.{MAP_REPO_TO_EXT[self.repo]}.{self.arch}.{val}:{self.env_image_tag}"

    @property
    def instance_image_key(self):
        key = f"sweb.eval.{self.arch}.{self.instance_id.lower()}:{self.instance_image_tag}"
        if self.is_remote_image:
            key = f"{self.namespace}/{key}".replace("__", "_1776_")
        return key

    @property
    def is_remote_image(self):
        return self.namespace is not None

    def get_instance_container_name(self, run_id=None):
        if not run_id:
            return f"sweb.eval.{self.instance_id}"
        return f"sweb.eval.{self.instance_id.lower()}.{run_id}"

    @property
    def base_dockerfile(self):
        return get_dockerfile_base(
            self.platform,
            self.arch,
            self.language,
            **{**DEFAULT_DOCKER_SPECS, **self.docker_specs},
        )

    @property
    def env_dockerfile(self):
        return get_dockerfile_env(
            self.platform,
            self.arch,
            self.language,
            self.base_image_key,
            **{**DEFAULT_DOCKER_SPECS, **self.docker_specs},
        )

    @property
    def instance_dockerfile(self):
        return get_dockerfile_instance(self.platform, self.language, self.env_image_key, self.copy_repo_from_host_path)

    @property
    def platform(self):
        if self.arch == "x86_64":
            return "linux/x86_64"
        elif self.arch == "arm64":
            return "linux/arm64/v8"
        else:
            raise ValueError(f"Invalid architecture: {self.arch}")


def get_test_specs_from_dataset(
    dataset: Union[list[SWEbenchInstance], list[TestSpec]],
    namespace: str = None,
    instance_image_tag: str = LATEST,
) -> list[TestSpec]:
    """
    Idempotent function that converts a list of SWEbenchInstance objects to a list of TestSpec objects.
    """
    if isinstance(dataset[0], TestSpec):
        return cast(list[TestSpec], dataset)
    return list(
        map(
            lambda x: make_test_spec(x, namespace, instance_image_tag),
            cast(list[SWEbenchInstance], dataset),
        )
    )


def make_test_spec(
    instance: SWEbenchInstance,
    namespace: str = None,
    base_image_tag: str = LATEST,
    env_image_tag: str = LATEST,
    instance_image_tag: str = LATEST
) -> TestSpec:
    """
    Create a test specification for a single instance of SWE-bench.
    
    Args:
        instance: The SWE-bench instance to create a test specification for
        namespace: The namespace to use for the instance image
        base_image_tag: The tag to use for the base image
        env_image_tag: The tag to use for the environment image
        instance_image_tag: The tag to use for the instance image
        skip_clone: If True, skip the git clone command
    """
    if isinstance(instance, TestSpec):
        return instance
    assert base_image_tag is not None, "base_image_tag cannot be None"
    assert env_image_tag is not None, "env_image_tag cannot be None"
    assert instance_image_tag is not None, "instance_image_tag cannot be None"
    instance_id = instance[KEY_INSTANCE_ID]
    repo = instance["repo"]
    version = instance.get("version")
    base_commit = instance["base_commit"]
    problem_statement = instance.get("problem_statement")
    hints_text = instance.get("hints_text")  # Unused
    test_patch = instance["test_patch"]

    def _from_json_or_obj(key: str) -> Any:
        """If key points to string, load with json"""
        if key not in instance:
            # If P2P, F2P keys not found, it's a validation instance
            return []
        if isinstance(instance[key], str):
            return json.loads(instance[key])
        return instance[key]

    pass_to_pass = _from_json_or_obj("PASS_TO_PASS")
    fail_to_pass = _from_json_or_obj("FAIL_TO_PASS")

    env_name = "testbed"
    repo_directory = f"/{env_name}"
    specs = MAP_REPO_VERSION_TO_SPECS[repo][version]
    docker_specs = specs.get("docker_specs", {})
    copy_repo_from_host_path = specs.get("copy_repo_from_host_path", None)
    

    skip_git_clone=copy_repo_from_host_path is not None

    repo_script_list = make_repo_script_list(
        specs, repo, repo_directory, base_commit, env_name, skip_git_clone
    )
    env_script_list = make_env_script_list(instance, specs, env_name)
    eval_script_list = make_eval_script_list(
        instance, specs, env_name, repo_directory, base_commit, test_patch
    )
    if platform.machine() in {"aarch64", "arm64"}:
        # use arm64 unless explicitly specified
        arch = "arm64" if instance_id not in USE_X86 else "x86_64"
    else:
        arch = "x86_64"

    return TestSpec(
        instance_id=instance_id,
        repo=repo,
        env_script_list=env_script_list,
        repo_script_list=repo_script_list,
        eval_script_list=eval_script_list,
        version=version,
        arch=arch,
        FAIL_TO_PASS=fail_to_pass,
        PASS_TO_PASS=pass_to_pass,
        language=MAP_REPO_TO_EXT[repo],
        docker_specs=docker_specs,
        namespace=namespace,
        base_image_tag=base_image_tag,
        env_image_tag=env_image_tag,
        instance_image_tag=instance_image_tag,
        copy_repo_from_host_path=copy_repo_from_host_path,
    )
