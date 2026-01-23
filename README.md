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
      image_name: ${{ matrix.image_name }}
      tag: ${{ matrix.tag }}
      runson: ${{ matrix.runson }}
      build-args: ${{ matrix.build-args }}
      image_prefix: 'flagbase'
      no-cache: ${{ matrix.no-cache }}
    secrets:
      REGISTRY_USERNAME: ${{ secrets.REGISTRY_USERNAME }}
      CONTAINER_REGISTRY: ${{ secrets.CONTAINER_REGISTRY }}
```
