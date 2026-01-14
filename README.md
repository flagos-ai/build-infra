# build-infra

[![Latest build status](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml/badge.svg?branch=main&event=push)](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml)

[![Schedule build status](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml/badge.svg?branch=main&event=schedule)](https://github.com/flagos-ai/build-infra/actions/workflows/trigger.yml)

This repo, currently is experiment for 

## base image

pipeline as code, and code as document.

| xPU | driver version | python | ubuntu | torch | file | image name | 
| --- | --- | --- | --- | --- | --- | --- |
| nv | 12.4.1 | latest | 22.04 | latest | container/containerfile.nvidia | harbor.baai.ac.cn/flagbase/flagbase-nvidia:latest |

## pipeline as code interface

Image and code build, basic CI to ensure the code works.

todo: how to use