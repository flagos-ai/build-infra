---
title: Overview
weight: 10
---

# Overview

## Image layers

- **base** — a vendor's SDK/toolkit + Python toolchain on an OS base. Built from
  `base/<vendor>-<backend>` by `base/build.py`, and tagged
  `flagos-base-<vendor>-<backend>:<version>-<revision>` (version/revision come
  from the containerfile's OCI labels).
- **runtime** — FlagGems installed on top of a base image (a separate flow).
- **app** — application layer (future).

## Naming & registry

All images go to a single registry configured in `.github/build-config.yml`,
differing only by a path prefix per layer (base images use `flagbase`).

## Source of truth

`configs.yaml` holds every backend's dependencies and image environment; each
`base/<name>` containerfile carries the OS + SDK install and the OCI
version/revision labels. The catalog and per-image reference in these docs are
generated from those files, so they always match what is built.
