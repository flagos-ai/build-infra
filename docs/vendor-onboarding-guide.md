# Vendor Onboarding Guide

This document describes how hardware vendors can integrate with the unified container image **build and push pipeline** by providing:

* a vendor configuration file (`vendor_json/<vendor>.json`)
* a container build file (`container/containerfile.<vendor>`)

Once submitted, CI automatically builds and publishes images to the centralized registry.

## Audience

**Target users:** GPU/accelerator/chip vendors who need to provide base runtime images.

## Overview

The image lifecycle is fully automated through CI:

1. Define a **configuration file** (`vendor_json/<vendor>.json`)
2. Provide a **Containerfile** (`container/containerfile.<vendor>`)
3. Submit a **PR or push**
4. CI **detects changes and builds**
5. Images are **automatically pushed** to the registry

Registry:

```
https://harbor.baai.ac.cn
```

## Repository Structure & Naming Conventions

### Configuration File (JSON)

| Item       | Requirement                                     |
| ---------- | ----------------------------------------------- |
| Path       | `vendor_json/<vendor>.json`                     |
| File name  | Must match vendor name (e.g., `nvidia.json`)    |
| image_name | `flagbase-<vendor>`                             |
| tag        | Semantic tags (e.g., `latest`, `py311torch2.6`) |

### Containerfile

| Item             | Requirement                        |
| ---------------- | ---------------------------------- |
| Path             | `container/containerfile.<vendor>` |
| Maintainer label | Required                           |
| Vendor name      | Must match JSON file               |

Required label:

```dockerfile
LABEL org.opencontainers.image.authors="FlagOS contributors"
```

### Consistency Requirement

The following must use the **same vendor identifier**:

```
vendor_json/<vendor>.json
container/containerfile.<vendor>
```

Example:

```
vendor_json/nvidia.json
container/containerfile.nvidia
```

## Step 1 — Define Configuration File

Create:

```
vendor_json/<vendor>.json
```

This file defines the **build matrix**. Multiple jobs are supported.

### Example (NVIDIA)

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

### Field Definitions

| Field         | Description                           | Example                  |
| ------------- | ------------------------------------- | ------------------------ |
| job_name      | CI job name                           | build-base-nvidia-latest |
| containerfile | Containerfile name under `container/` | containerfile.nvidia     |
| image_name    | Image name                            | flagbase-nvidia          |
| tag           | Image tag                             | latest                   |
| runson        | GitHub runner label                   | h20      |
| build-args    | Build arguments (newline separated)   | PYTHON_VERSION=3.12      |

### Naming Recommendation

```
job_name = build-base-<vendor>-<tag>
image_name = flagbase-<vendor>
```

## Step 2 — Define Containerfile

Create:

```
container/containerfile.<vendor>
```

### Example (NVIDIA)

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

### Required Components

#### Mandatory

```dockerfile
LABEL org.opencontainers.image.authors="FlagOS contributors"
```

#### General Requirements

All vendor images should:

* Use **Ubuntu 24.04** (or compatible official image)
* Install Python and pip
* Install PyTorch
* Use `/workspace` as working directory
* Provide build toolchain

#### Version Control via Build Args

| Arg            | Purpose         |
| -------------- | --------------- |
| PYTHON_VERSION | Python version  |
| TORCH_VERSION  | PyTorch version |

#### Vendor Requirements

Install vendor-specific:

* GPU drivers
* SDKs
* runtime libraries

> Note: Official vendor base images may already include these components.

## CI Trigger & Push Strategy

### Push / PR

When files change:

```
vendor_json/**
container/**
```

CI will:

* detect affected vendors
* build only related jobs
* NOT push images (validation only)

### Scheduled Build

Daily:

```
01:00
```

Behavior:

* full rebuild
* push images
* no cache

Parameters:

```
push=true
no-cache=true
```

Used to refresh base images.

### Image Registry

Registry:

```
harbor.baai.ac.cn
```

Image naming format:

```
${REGISTRY}/${image_prefix}/${image_name}:${tag}
```

Default:

```
image_prefix = flagbase
```

Example:

```
harbor.baai.ac.cn/flagbase/flagbase-nvidia:latest
```
