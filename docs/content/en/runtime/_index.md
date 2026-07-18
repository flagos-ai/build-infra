---
title: Runtime images
weight: 30
---

<!--
 Copyright 2026 FlagOS Contributors

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 -->


A **runtime image** is built on top of a [base image]({{< relref "/base" >}}) and adds
the **Python interpreter** and the **software stack** — Torch, Triton, FlagTree, and
FlagGems.

Pick a backend to see its Python version, software stack, dependencies, and how to run it:

{{< runtime-catalog >}}
