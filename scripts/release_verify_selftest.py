#!/usr/bin/env python3
# Copyright 2026 FlagOS Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Self-test for the verify step of the native release workflows.
#
# That step is the gate publishing depends on, and the workflows carrying it are
# dispatch-only, so nothing runs it on a pull request. This checks outer shell
# syntax on the workflow step, builds tiny fixture packages covering both valid
# plugin/private layouts and load-path failure modes, and runs the step as the
# workflow writes it against each.
#
# Usage: release_verify_selftest.py [WORKFLOW ...]   (default: all)
# Needs docker.

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = {
    'native-deb': ('deb', 'ubuntu:24.04'),
    'native-rpm': ('rpm', 'fedora:43'),
    'flagcx-rpm': ('rpm', 'fedora:43'),
}

# name, packages installed together, expected to pass, text the output must carry
CASES = [
    ('clean',        ['fxok'],                         True,  'links resolve'),
    ('left-to-env',  ['fxenv'],                        True,  'symbols not checked'),
    ('undefined',    ['fxundef'],                      False, 'has undefined symbols'),
    ('no-library',   ['fxdoc'],                        False, 'no shared library shipped'),
    ('undeclared',   ['fxdep', 'fxdep-tools', 'fxuse-bare'], False, 'but not declared'),
    ('declared',     ['fxdep', 'fxuse', 'fxuse-devel'], True, 'nothing undeclared'),
    # Valid private DT_NEEDED and RTLD_GLOBAL dlopen-host plugin layouts
    ('self-priv-ok', ['fxselfpriv'],                   True,  'shipped by the package itself'),
    ('plugin-host',  ['fxplughost'],                   True,  'links resolve'),
    ('sub-plugin',   ['fxsubplug'],                    True,  'links resolve'),
    ('triton-plug',  ['fxtritonplug'],                 True,  'links resolve'),
    # Load-path counterexamples that fail under real dynamic linking / dlopen
    ('pub-norpath',  ['fxpubnorpath'],                 False, 'no RUNPATH to reach it'),
    ('pub-samesym',  ['fxpubsamesym'],                 False, 'has undefined symbols'),
    ('nonhost-sym',  ['fxnonhostsym'],                 False, 'has undefined symbols'),
    ('sib-samesym',  ['fxsibsamesym'],                 False, 'has undefined symbols'),
    ('split-hosts',  ['fxsplitplug'],                  False, 'has undefined symbols'),
    ('symver-miss',  ['fxsymver'],                     False, 'symbol version mismatch'),
]

BUILD_LIBS = r"""
set -e
cd /src
echo 'int fx_ok(void){return 1;}'                                                  > ok.c
echo 'int fx_ghost(void){return 1;}'                                               > ghost.c
echo 'int fx_ghost(void); int fx_env(void){return fx_ghost();}'                    > env.c
echo 'int fx_missing(void); int fx_undef(void){return fx_missing();}'              > undef.c
echo 'int fx_dep(void){return 1;}'                                                 > dep.c
echo 'int fx_dep(void); int fx_use(void){return fx_dep();}'                        > use.c
echo 'int fx_priv(void){return 7;}'                                                > priv.c
echo 'int fx_priv(void); int fx_child(void){return fx_priv();}'                    > child.c
echo 'FXV1 { global: fx_host_api; fx_host_load; local: *; };'                      > host.ver
cat > host.c <<'EOF'
#include <dlfcn.h>
int fx_host_api(void) { return 42; }
void *fx_host_load(const char *p) { return dlopen(p, RTLD_NOW | RTLD_GLOBAL); }
EOF
echo 'int fx_host_api(void); int fx_plug_entry(void){return fx_host_api();}'       > plug.c
echo 'int fx_accidental(void){return 9;}'                                          > unrelated.c
echo 'int fx_accidental(void); int fx_pub_caller(void){return fx_accidental();}'   > pubcaller.c
cat > sibhost.c <<'EOF'
#include <dlfcn.h>
int fx_accidental(void) { return 9; }
void *fx_sib_load(const char *p) { return dlopen(p, RTLD_NOW | RTLD_GLOBAL); }
EOF
echo 'int fx_host_api(void); int fx_accidental(void); int fx_both(void){return fx_host_api()+fx_accidental();}' > splitplug.c
cc() { gcc -shared -fPIC -o "$1" -Wl,-soname,"$1" "${@:2}"; }
cc libfxok.so.1        ok.c
cc libfxghost.so.1     ghost.c
cc libfxenv.so.1       env.c       -L. -l:libfxghost.so.1
cc libfxundef.so.1     undef.c
cc libfxdep.so.1       dep.c
cc libfxuse.so.1       use.c       -L. -l:libfxdep.so.1
cc libfxpriv.so.1      priv.c
cc libfxchild.so.1     child.c     -L. -l:libfxpriv.so.1
cc libfxhost.so.1      host.c      -Wl,--version-script,host.ver -ldl
gcc -shared -fPIC -o fxplugin.so plug.c
cc libfxunrelated.so.1 unrelated.c
cc libfxpubcaller.so.1 pubcaller.c
gcc -shared -fPIC -o fxbadplug.so pubcaller.c
cc libfxsibhost.so.1   sibhost.c   -ldl
gcc -shared -fPIC -o fxsplitplug.so splitplug.c
mkdir -p v2
echo 'FXVER_1.0 { global: fx_v1; local: *; };' > ver1.map
echo 'FXVER_1.0 { global: fx_v1; local: *; }; FXVER_2.0 { global: fx_v2; } FXVER_1.0;' > ver2.map
echo 'int fx_v1(void){return 1;}' > ver1.c
echo 'int fx_v1(void){return 1;} int fx_v2(void){return 2;}' > ver2.c
echo 'int fx_v2(void); int fx_use_v2(void){return fx_v2();}' > symver.c
cc libfxver.so.1       ver1.c      -Wl,--version-script,ver1.map
gcc -shared -fPIC -o v2/libfxver.so.1 -Wl,-soname,libfxver.so.1 ver2.c -Wl,--version-script,ver2.map
cc libfxsymver.so.1    symver.c    -Lv2 -l:libfxver.so.1
"""


def packages(libdir):
    return {
        'fxok':         ([('libfxok.so.1', libdir)], [], '', ''),
        'fxenv':        ([('libfxenv.so.1', libdir)], [], '', ''),
        'fxundef':      ([('libfxundef.so.1', libdir)], [], '', ''),
        'fxdoc':        ([('ok.c', '/usr/share/doc/fxdoc')], [], '', ''),
        'fxdep':        ([('libfxdep.so.1', '/opt/fxdep/lib')], [],
                         'Provides: libfxdep.so.1()(64bit)', ''),
        'fxdep-tools':  ([('libfxok.so.1', '/opt/fxdeptools/lib')], [], '', ''),
        'fxuse-bare':   ([('libfxuse.so.1', libdir)], [],
                         'Requires: fxdep-tools', 'fxdep-tools'),
        'fxuse':        ([('libfxuse.so.1', libdir)], [],
                         'Requires: libfxdep.so.1()(64bit)', 'fxdep'),
        'fxuse-devel':  ([], [(f'{libdir}/libfxuse.so', 'libfxuse.so.1')],
                         'Requires: fxuse', 'fxuse'),
        'fxselfpriv':   ([('libfxpriv.so.1', '/opt/fxself/deps'),
                          ('libfxchild.so.1', '/opt/fxself/lib')], [],
                         'Provides: libfxpriv.so.1()(64bit)', ''),
        'fxplughost':   ([('libfxhost.so.1', libdir),
                          ('fxplugin.so', '/opt/fxplug/plugins')], [], '', ''),
        'fxsubplug':    ([('libfxhost.so.1', libdir),
                          ('fxplugin.so', f'{libdir}/fxplug/plugins')], [], '', ''),
        'fxtritonplug': ([('libfxhost.so.1', '/opt/fxtriton/_C'),
                          ('fxplugin.so', '/opt/fxtriton/backends/metax')], [], '', ''),
        'fxpubnorpath': ([('libfxpriv.so.1', '/opt/fxpubbad/deps'),
                          ('libfxchild.so.1', libdir)], [],
                         'Provides: libfxpriv.so.1()(64bit)', ''),
        'fxpubsamesym': ([('libfxunrelated.so.1', libdir),
                          ('libfxpubcaller.so.1', libdir)], [], '', ''),
        'fxnonhostsym': ([('libfxunrelated.so.1', libdir),
                          ('fxbadplug.so', '/opt/fxnonhost/plugins')], [], '', ''),
        'fxsibsamesym': ([('libfxsibhost.so.1', '/opt/fxsib/backends/a'),
                          ('fxbadplug.so', '/opt/fxsib/backends/b')], [], '', ''),
        'fxsplitplug':  ([('libfxhost.so.1', libdir),
                          ('libfxsibhost.so.1', libdir),
                          ('fxsplitplug.so', '/opt/fxsplit/plugins')], [], '', ''),
        'fxsymver':     ([('libfxver.so.1', libdir),
                          ('libfxsymver.so.1', libdir)], [], '', ''),
    }


def rpm_script():
    lines = ['dnf install -y -q gcc rpm-build > /dev/null', BUILD_LIBS, 'mkdir -p /work']
    for name, (files, links, deps, _) in packages('/usr/lib64').items():
        install = [f'install -D -m 0755 /src/{src} %{{buildroot}}{dst}/{src}' for src, dst in files]
        install += [f'mkdir -p %{{buildroot}}$(dirname {l}) && ln -s {t} %{{buildroot}}{l}' for l, t in links]
        listed = [f'{dst}/{src}' for src, dst in files] + [l for l, _ in links]
        spec = '\n'.join([
            f'Name: {name}', 'Version: 1', 'Release: 1', 'License: Apache-2.0',
            'Summary: verify self-test fixture', 'AutoReqProv: no', deps,
            '%global debug_package %{nil}', '%global __os_install_post %{nil}',
            '%description', 'verify self-test fixture',
            '%install', *install, '%files', *listed, '',
        ])
        lines.append(f"cat > /work/{name}.spec <<'SPEC'\n{spec}SPEC")
        lines.append(f'rpmbuild -bb -D "_topdir /work/top" -D "_rpmdir /out" '
                     f'-D "_build_name_fmt {name}.rpm" /work/{name}.spec > /dev/null')
    return '\n'.join(lines)


def deb_script():
    libdir = '/usr/lib/x86_64-linux-gnu'
    lines = ['apt-get update -qq && apt-get install -y -qq gcc > /dev/null', BUILD_LIBS]
    for name, (files, links, _, depends) in packages(libdir).items():
        stage = f'/work/{name}'
        control = '\n'.join(filter(None, [
            f'Package: {name}', 'Version: 1', 'Architecture: amd64',
            'Maintainer: FlagOS Contributors <flagos@baai.ac.cn>',
            f'Depends: {depends}' if depends else '',
            'Description: verify self-test fixture',
        ])) + '\n'
        lines.append(f'mkdir -p {stage}/DEBIAN')
        lines.append(f"cat > {stage}/DEBIAN/control <<'CTRL'\n{control}CTRL")
        lines += [f'install -D -m 0755 /src/{src} {stage}{dst}/{src}' for src, dst in files]
        lines += [f'mkdir -p {stage}$(dirname {l}) && ln -s {t} {stage}{l}' for l, t in links]
        lines.append(f'dpkg-deb --build --root-owner-group {stage} /out/{name}.deb > /dev/null')
    return '\n'.join(lines)


def docker(image, script, mounts=()):
    cmd = ['docker', 'run', '--rm', '--platform', 'linux/amd64']
    for host, target, mode in mounts:
        cmd += ['-v', f'{host}:{target}:{mode}']
    return subprocess.run(cmd + [image, 'bash', '-c', script],
                          capture_output=True, text=True)


def verify_script(workflow):
    # Validate outer step syntax, helper script syntax, and inner docker-run body.
    helper = ROOT / 'scripts/verify-elf-links.sh'
    helper_check = subprocess.run(['bash', '-n', str(helper)], capture_output=True, text=True)
    if helper_check.returncode != 0:
        sys.exit(f'scripts/verify-elf-links.sh failed bash -n:\n{helper_check.stderr}')
    doc = yaml.safe_load((ROOT / f'.github/workflows/{workflow}.yml').read_text())
    runs = [s['run'] for s in doc['jobs']['verify']['steps']
            if 'docker run' in s.get('run', '')]
    if len(runs) != 1:
        sys.exit(f'{workflow}: expected one docker-run step in verify, found {len(runs)}')
    run = runs[0]
    if 'scripts/verify-elf-links.sh:/verify-elf-links.sh:ro' not in run:
        sys.exit(f'{workflow}: verify docker-run step does not mount scripts/verify-elf-links.sh')
    outer_check = subprocess.run(
        ['bash', '-n'],
        input=re.sub(r'\$\{\{[^}]+\}\}', 'placeholder', run),
        capture_output=True, text=True,
    )
    if outer_check.returncode != 0:
        sys.exit(f'{workflow}: outer verify step failed bash -n:\n{outer_check.stderr}')
    body = run[run.index("bash -c '") + len("bash -c '"):run.rindex("'")]
    if '${{' in body:
        sys.exit(f'{workflow}: the verify script uses an expression this test cannot supply')
    unescaped = body.replace("'\"'\"'", "")
    if "'" in unescaped:
        sys.exit(f'{workflow}: unescaped single quote inside bash -c body would truncate the script')
    inner_check = subprocess.run(['bash', '-n'], input=body.replace("'\"'\"'", "'"),
                                 capture_output=True, text=True)
    if inner_check.returncode != 0:
        sys.exit(f'{workflow}: inner verify body failed bash -n:\n{inner_check.stderr}')
    return body.replace("'\"'\"'", "'")


def main(selected):
    failures = 0
    work = pathlib.Path(tempfile.mkdtemp(prefix='verify-selftest-'))
    built = {}
    helper = ROOT / 'scripts/verify-elf-links.sh'
    try:
        for workflow in selected:
            kind, image = WORKFLOWS[workflow]
            script = verify_script(workflow)
            if kind not in built:
                src, out = work / f'{kind}-src', work / f'{kind}-out'
                src.mkdir(), out.mkdir()
                r = docker(image, deb_script() if kind == 'deb' else rpm_script(),
                           [(src, '/src', 'rw'), (out, '/out', 'rw')])
                absent = [p for p in packages('') if not (out / f'{p}.{kind}').exists()]
                if r.returncode or absent:
                    sys.exit(f'building {kind} fixtures failed (missing: {absent}):\n'
                             f'{r.stdout}{r.stderr}')
                built[kind] = out
            for case, pkgs, should_pass, marker in CASES:
                case_dir = work / f'{workflow}-{case}'
                case_dir.mkdir()
                for p in pkgs:
                    shutil.copy(built[kind] / f'{p}.{kind}', case_dir)
                r = docker(image, script,
                           [(case_dir, '/pkg', 'ro'), (helper, '/verify-elf-links.sh', 'ro')])
                output = r.stdout + r.stderr
                ok = (r.returncode == 0) == should_pass and marker in output
                print(f"{'PASS' if ok else 'FAIL'}  {workflow:11} {case:12} "
                      f"(exit {r.returncode}, expected {'0' if should_pass else 'non-zero'})")
                if not ok:
                    failures += 1
                    print(f'      expected to see: {marker!r}')
                    print('      ' + '\n      '.join(output.strip().splitlines()[-8:]))
    finally:
        subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                        '-v', f'{work}:/w', 'ubuntu:24.04',
                        'bash', '-c', 'rm -rf /w/*'], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)
    return 1 if failures else 0


if __name__ == '__main__':
    names = sys.argv[1:] or list(WORKFLOWS)
    unknown = [n for n in names if n not in WORKFLOWS]
    if unknown:
        sys.exit(f'unknown workflow(s): {unknown}; known: {list(WORKFLOWS)}')
    sys.exit(main(names))
