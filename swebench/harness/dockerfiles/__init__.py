from swebench.harness.dockerfiles.javascript import (
    _DOCKERFILE_BASE_JS,
    _DOCKERFILE_ENV_JS,
    _DOCKERFILE_INSTANCE_JS,
)

from swebench.harness.dockerfiles.python import (
    _DOCKERFILE_BASE_PY,
    _DOCKERFILE_ENV_PY,
    _DOCKERFILE_INSTANCE_PY,
)

_DOCKERFILE_BASE = {
    "py": _DOCKERFILE_BASE_PY,
    "js": _DOCKERFILE_BASE_JS,
}

_DOCKERFILE_ENV = {
    "py": _DOCKERFILE_ENV_PY,
    "js": _DOCKERFILE_ENV_JS,
}

_DOCKERFILE_INSTANCE = {
    "py": _DOCKERFILE_INSTANCE_PY,
    "js": _DOCKERFILE_INSTANCE_JS,
}


def get_dockerfile_base(platform, arch, language, **kwargs):
    if arch == "arm64":
        conda_arch = "aarch64"
    else:
        conda_arch = arch
    return _DOCKERFILE_BASE[language].format(
        platform=platform, conda_arch=conda_arch, **kwargs
    )


def get_dockerfile_env(platform, arch, language, base_image_key, **kwargs):
    return _DOCKERFILE_ENV[language].format(
        platform=platform,
        arch=arch,
        base_image_key=base_image_key,
        **kwargs,
    )


def get_dockerfile_instance(platform, language, env_image_name, copy_repo_from_host_path=None):
    if copy_repo_from_host_path is not None:
        copy_cmd=f"COPY {copy_repo_from_host_path}/. /testbed/"
    else:
        copy_cmd=""
    docker_file=_DOCKERFILE_INSTANCE[language].format(
        platform=platform, env_image_name=env_image_name, copy_cmd=copy_cmd
    )
    return docker_file
