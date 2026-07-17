---
title: Base images
weight: 20
---

A **base image** is a vendor's SDK and toolchain installed on an operating-system
base. It's only about the **OS** and the **supported SDK version** — not Python,
Torch, or Triton (those belong to the [runtime images]({{< relref "/runtime" >}})).

Pick a backend to see its contents (OS, SDK packages, environment) and how to run it:

{{< base-catalog >}}
