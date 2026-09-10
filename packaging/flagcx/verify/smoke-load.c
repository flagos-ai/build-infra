/* Copyright 2026 FlagOS Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Load the installed libflagcx through the default loader path and call it.
 *
 * RTLD_NOW is the point of this file: lazy binding would let a vendor library
 * that is absent or mismatched survive until the first collective, which is a
 * failure on a customer's node rather than here.
 *
 * The name is dlopen'd bare, not by path, so this also proves the soname
 * symlink the package ships is what the loader resolves.
 */
#include <dlfcn.h>
#include <stdio.h>

typedef int (*flagcx_get_version_fn)(int *);

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: smoke-load <libflagcx.so.N>\n");
        return 2;
    }

    void *lib = dlopen(argv[1], RTLD_NOW);
    if (lib == NULL) {
        fprintf(stderr, "dlopen(%s, RTLD_NOW) failed: %s\n", argv[1], dlerror());
        return 1;
    }

    flagcx_get_version_fn get_version =
        (flagcx_get_version_fn)dlsym(lib, "flagcxGetVersion");
    if (get_version == NULL) {
        fprintf(stderr, "flagcxGetVersion not found: %s\n", dlerror());
        return 1;
    }
    /* Present but never called: initializing a communicator needs a device. */
    if (dlsym(lib, "flagcxCommInitRank") == NULL) {
        fprintf(stderr, "flagcxCommInitRank not found: %s\n", dlerror());
        return 1;
    }

    int version = 0;
    int rc = get_version(&version);
    /* Only the call is asserted, not the number: flagcx.h's FLAGCX_VERSION_*
     * constants lag the release tags, so comparing them would fail on a
     * correct package. The encoding is the header's own (major*10000+...). */
    if (rc != 0) {
        fprintf(stderr, "flagcxGetVersion returned %d, want 0 (flagcxSuccess)\n", rc);
        return 1;
    }

    printf("ok: flagcxGetVersion reports %d.%d.%d\n",
           version / 10000, version / 100 % 100, version % 100);
    return 0;
}
