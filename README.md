# build-infra

[![Latest build status](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml/badge.svg?branch=main&event=push)](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml)

[![Schedule build status](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml/badge.svg?branch=main&event=schedule)](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml)

This repo, currently is experiment for 

## base image

pipeline as code, and code as document.

| xPU | driver version | python | ubuntu | torch | file | image name | 
| --- | --- | --- | --- | --- | --- | --- |
| nvidia | cuda-drivers=590.48.01-0ubuntu1 cuda-toolkit=13.1.1-1 libnccl2=2.29.2-1+cuda13.1 libnccl-dev=2.29.2-1+cuda13.1 | latest | 24.04 | latest | container/containerfile.nvidia | harbor.baai.ac.cn/flagbase/flagbase-nvidia:latest |
| nvidia | cuda-drivers=590.48.01-0ubuntu1 cuda-toolkit=13.1.1-1 libnccl2=2.29.2-1+cuda13.1 libnccl-dev=2.29.2-1+cuda13.1 | 3.12 | 24.04 | 2.8 | container/containerfile.nvidia | harbor.baai.ac.cn/flagbase/flagbase-nvidia:py312torch2.8 |
| metax | maca_sdk=3.3.0.15 | latest | 22.04 | latest | container/containerfile.metax | harbor.baai.ac.cn/flagbase/flagbase-metax:latest |
| amd | rocm-hip-libraries=7.1.1.70101-38~22.04 rocm-hip-runtime=7.1.1.70101-38~22.04 rocm-language-runtime=7.1.1.70101-38~22.04 rocm-hip-sdk=7.1.1.70101-38~22.04 rocm-opencl-runtime=7.1.1.70101-38~22.04 rocm-developer-tools=7.1.1.70101-38~22.04 rocm-opencl-sdk=7.1.1.70101-38~22.04 | latest | 24.04 | latest | container/containerfile.amd | harbor.baai.ac.cn/flagbase/flagbase-amd:latest |

## pipeline as code interface

Image and code build, basic CI to ensure the code works.

ref https://docs.github.com/zh/actions/how-tos/reuse-automations/reuse-workflows

```
jobs:
  call-workflow-passing-data:
    uses: flagos-ai/build-infra/.github/workflows/imagebuild.yml@main
    with:
      push: ${{ matrix.push }}
      containerfile: ${{ matrix.containerfile }}
      tag: ${{ matrix.tag }}
      label: ${{ matrix.label }}
      runson: ${{ matrix.runson }}
      build-args: ${{ matrix.build-args }}
      image_prefix: 'flagbase'
      build-args: ""
    secrets:
      REGISTRY_USERNAME: ${{ secrets.REGISTRY_USERNAME }}
      CONTAINER_REGISTRY: ${{ secrets.CONTAINER_REGISTRY }}
```


## contribute a new base image(early draft)
1. impls your container file, from template below:
```dockerfile
# A base image, better to be ubuntu
FROM ubuntu:24.04
# MAINTAINER
MAINTAINER "flagos contributors"
# FlagOS build args
ARG PYTHON_VERSION=3
ARG TORCH_VERSION=latest
# noninteractive to make apt-get work
ENV DEBIAN_FRONTEND=noninteractive
RUN set -x
# base dependencies or tool chains
RUN apt-get update -y && \
    apt-get install -y --allow-change-held-packages \
    python${PYTHON_VERSION} \
    python3-pip \
    python${PYTHON_VERSION}-venv \
    git \
    autotools-dev \
    wget \
    gcc \
    g++ \
    build-essential \
    cmake && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN if [ "$PYTHON_VERSION" != "3" ]; then \
        ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python3; \
    fi && \
    ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python
# device specific with clean up
# RUN steps for device driver
# RUN steps for device sdk
# workdir
WORKDIR /workspace

# py build tools
RUN pip install -U scikit-build-core>=0.11 pybind11 --break-system-packages
# torch
RUN if [ "$TORCH_VERSION" = "latest" ]; then \
        pip install -U torch --break-system-packages; \
    else \
        pip install -U torch==$TORCH_VERSION --break-system-packages; \
    fi

```
2. update README table above(## base image)
3. Impls your own build trigger.(Same as ## pipeline as code interface)
as a dynamic way to set up matrix strategy workflow as https://github.com/orgs/community/discussions/38088
```json
{ 
  "job_name": "build-base-nvidia-image", 
  "push": "false",
  "containerfile": "containerfile.nvidia",
  "tag": "flagbase-nvidia",
  "label": "latest",
  "runson": "h20",
  "build-args": ""
}
```
4. Updates json in steps 3 in trigger and scheduled CI trigger.