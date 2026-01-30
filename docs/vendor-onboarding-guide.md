# Vendor Onboarding Guide

This document describes how hardware vendors can integrate with the unified container image **build and push pipeline** by providing:

* A vendor configuration file (`vendor_json/<vendor>.json`)
* A container build file (`container/containerfile.<vendor>`)

Once submitted, CI automatically builds and publishes images to the centralized registry.

## Audience

**Target users:** GPU/accelerator/chip vendors who need to provide base runtime images.

## Overview

The image lifecycle is fully automated through CI:

1. Define a configuration file (`vendor_json/<vendor>.json`).
2. Provide a containerfile (`container/containerfile.<vendor>`).
3. Submit a PR.
4. CI detects changes and builds images.
5. Images are automatically pushed to the registry (<https://harbor.baai.ac.cn>)

## Repository structure & naming conventions

### Configuration file (JSON)

| Item      | Requirement                                         |
|-----------|-----------------------------------------------------|
| Path      | `vendor_json/<vendor>.json`                         |
| File name | Must match vendor name (for example, `nvidia.json`) |

### Containerfile

| Item             | Requirement                                                              |
|------------------|--------------------------------------------------------------------------|
| Path             | `container/containerfile.<vendor>`                                       |
| File name        | Must match vendor name (for example, `container/containerfile.<vendor>`) |
| Maintainer label | `LABEL org.opencontainers.image.authors="FlagOS contributors"`           |

## Consistency requirement

The following must use the same vendor identifier:

```
vendor_json/<vendor>.json
container/containerfile.<vendor>
```

Example:

```
vendor_json/nvidia.json
container/containerfile.nvidia
```

## Define configuration file

1. Create the `<vendor>.json` file under `vendor_json/`.

    This file defines the build matrix. Multiple jobs are supported.

    **Example: Configuration file (NVIDIA)**

    ```json
    [
    {
        "job_name": "build-base-nvidia-image",
        "containerfile": "containerfile.nvidia",
        "image_name": "flagbase-nvidia",
        "tag": "latest",
        "runson": "h20",
        "build-args": ""
    },
    {
        "job_name": "build-base-nvidia-image-py312torch2.8",
        "containerfile": "containerfile.nvidia",
        "image_name": "flagbase-nvidia",
        "tag": "py312torch2.8",
        "runson": "h20",
        "build-args": "PYTHON_VERSION=3.12\nTORCH_VERSION=2.8"
    }
    ]
    ```

2. Specify the following fields as needed.

    | Field         | Description                                                    | Example                     |
    |---------------|----------------------------------------------------------------|-----------------------------|
    | job_name      | CI job name. Recommended: `build-base-<vendor>-<tag>`          | `build-base-nvidia-latest`  |
    | containerfile | Containerfile name under `container/`                          | `containerfile.nvidia`      |
    | image_name    | Image name. Recommended: `flagbase-<vendor>`                   | `flagbase-nvidia`           |
    | tag           | Image tag                                                      | `latest` or `py312torch2.8` |
    | runson        | GitHub runner label                                            | `h20`                       |
    | build-args    | Build arguments. Use newline (`\n`) separated KEY=VALUE pairs | `PYTHON_VERSION=3.12`       |

## Define containerfile

1. Create the `containerfile.<vendor>` file under `container/.`

    **Example: Containerfile (NVIDIA)**

    ```dockerfile
    FROM ubuntu:24.04

    LABEL org.opencontainers.image.authors="FlagOS contributors"

    ARG PYTHON_VERSION=3
    ARG TORCH_VERSION=latest

    ENV DEBIAN_FRONTEND=noninteractive

    # Base dependencies
    RUN apt-get update -y && \
        apt-get install -y \
        python${PYTHON_VERSION} \
        python3-pip \
        wget && \
        apt-get clean && \
        rm -rf /var/lib/apt/lists/*

    # Python symlink
    RUN ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python

    # PyTorch installation
    RUN if [ "$TORCH_VERSION" = "latest" ]; then \
            pip install -U torch --break-system-packages; \
        else \
            pip install -U torch==$TORCH_VERSION --break-system-packages; \
        fi

    # NVIDIA drivers & CUDA
    RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb && \
        dpkg -i cuda-keyring_1.1-1_all.deb && \
        apt-get update -y && \
        apt-get install -y cuda-drivers cuda-toolkit libnccl2 libnccl-dev

    WORKDIR /workspace

    # Toolchain
    RUN apt-get update -y && \
        apt-get install -y \
        autotools-dev gcc g++ build-essential cmake && \
        pip install -U scikit-build-core>=0.11 pybind11
    ```

2. Specify the following information as needed.

    * **Label**

        Must be `FlagOS contributors`.

        ```dockerfile
        LABEL org.opencontainers.image.authors="FlagOS contributors"
        ```

    * **General configuration**

        All vendor images should include:

        * Base image: **Ubuntu 24.04** (or compatible official image)
        * Python and pip
        * PyTorch
        * `/workspace` as working directory
        * Build toolchain

    * **Vendor-specific configuration**

      * GPU drivers
      * SDKs

       > Note: Official vendor base images may already include these components.
