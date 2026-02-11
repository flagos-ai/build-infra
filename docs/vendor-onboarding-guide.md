# Vendor Onboarding Guide

This document describes how hardware vendors can integrate with the unified container image **build and push pipeline** by providing the following:

- A vendor configuration file (`vendor_json/<vendor>.json`)
- A container build file (`container/containerfile.<vendor>`)

Once submitted, CI automatically builds and publishes images to the centralized registry.

## Audience

**Target users:** GPU/accelerator/chip vendors who need to provide base runtime images.

## Overview

The image lifecycle is fully automated through CI:

1. Define a configuration file (`vendor_json/<vendor>.json`).
1. Provide a containerfile (`container/containerfile.<vendor>`).
1. Submit a PR.
1. The CI detects changes and builds images.
1. Images are automatically pushed to the registry (<https://harbor.baai.ac.cn>).

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

## Consistency requirement

You must use the same vendor identifier when naming the configuration file and the containerfile:

```
vendor_json/<vendor>.json
container/containerfile.<vendor>
```

Example:

```
vendor_json/nvidia.json
container/containerfile.nvidia
```

## Define the Configuration File

1. Navigate to the [vendor_json](../vendor_json) directory where all configuration files are located.
1. In your AI assistant chat window, perform the following steps:

   1. Copy the content of an existing vendor configuration file (for example, `nvidia.json`) into the chat.
   2. Use the following prompt template, amended with your vendor details, to generate a new configuration file:

      ```
      I am a developer for <vendor> graphics cards. Please reference the provided NVIDIA configuration file to write a configuration file for <vendor> graphics cards.

      Required Python versions are 3.10 to 3.12. Required PyTorch versions are 2.8 to 2.9.

      The containerfile must strictly follow the original containerfile structure. Keep it concise without extra configuration.
      ```

      **Example for generating an `amd.json` file based on `nvidia.json`:**

      ```
      *[Pasted content of nvidia.json]*

      I am a developer for AMD graphics cards. Please reference the provided NVIDIA configuration file to write a configuration file for AMD graphics cards.

      Required Python versions are 3.10 to 3.12. Required PyTorch versions are 2.8 to 2.9.

      The containerfile must strictly follow the original containerfile structure. Keep it concise without extra configuration.
      ```

1. Create a new file `vendor_json/<vendor>.json` and paste the generated configuration content into it.

## Define the Containerfile

1. Navigate to the [container](../container) directory where all containerfiles are located.
1. In your AI assistant chat window, perform the following steps:

   1. Copy the content of an **existing containerfile** (for example, `containerfile.nvidia`) into the chat.
   1. Use the following prompt template, amended with your vendor's specific download URLs, to generate a new containerfile:

      ```
      I am a developer for <vendor> graphics cards. Please reference the provided NVIDIA containerfile to write a containerfile for <vendor> graphics cards.

      Required Python versions are 3.10 to 3.12.
      Required PyTorch versions are 2.8 to 2.9.
      The driver download URL is: https://<vendor>.com/<vendor>_driver.tar
      The SDK download URL is: https://<vendor>.com/<vendor>_sdk.tar

      The containerfile must strictly follow the original containerfile structure. Keep it concise without extra configuration.
      ```

      **Example for generating a `containerfile.amd` based on `containerfile.nvidia`:**

      ```
      *[Pasted content of containerfile.nvidia]*

      I am a developer for AMD graphics cards. Please reference the provided NVIDIA containerfile to write a containerfile for AMD graphics cards.

      Required Python versions are 3.10 to 3.12.
      Required PyTorch versions are 2.8 to 2.9.
      The driver download URL is: https://amd.com/amd_driver.tar
      The SDK download URL is: https://amd.com/amd_sdk.tar

      The containerfile must strictly follow the original containerfile structure. Keep it concise without extra configuration.
      ```

1. Create a new file `container/containerfile.<vendor>` and paste the generated containerfile content into it.

   > ![Important]
   > Ensure the generated containerfile includes the following label:
   > 
   > The `LABEL` directive `org.opencontainers.image.authors` must be set to `FlagOS contributors`.
