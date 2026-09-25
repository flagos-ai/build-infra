import importlib.metadata
import importlib.util
import sys

dist = importlib.metadata.distribution("megatron-core")
root = dist.locate_file("")
so = sorted((root / "megatron/core/datasets").glob("helpers_cpp*.so"))
assert so, "helpers_cpp .so not found in the installed wheel"
spec = importlib.util.spec_from_file_location("helpers_cpp", str(so[0]))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert callable(mod.build_sample_idx_int32), "build_sample_idx_int32 not bound"
assert callable(mod.build_sample_idx_int64), "build_sample_idx_int64 not bound"
assert callable(mod.build_exhaustive_blending_indices), "build_exhaustive_blending_indices not bound"
print("OK helpers_cpp", mod.__file__)
