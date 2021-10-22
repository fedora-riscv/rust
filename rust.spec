# Only x86_64 and i686 are Tier 1 platforms at this time.
# https://doc.rust-lang.org/nightly/rustc/platform-support.html
%global rust_arches x86_64 i686 armv7hl aarch64 ppc64 ppc64le s390x

# The channel can be stable, beta, or nightly
%{!?channel: %global channel stable}

# To bootstrap from scratch, set the channel and date from src/stage0.txt
# e.g. 1.10.0 wants rustc: 1.9.0-2016-05-24
# or nightly wants some beta-YYYY-MM-DD
# Note that cargo matches the program version here, not its crate version.
%global bootstrap_rust 1.55.0
%global bootstrap_cargo 1.55.0
%global bootstrap_channel 1.55.0
%global bootstrap_date 2021-09-09

# Only the specified arches will use bootstrap binaries.
#global bootstrap_arches %%{rust_arches}

# Define a space-separated list of targets to ship rust-std-static-$triple for
# cross-compilation. The packages are noarch, but they're not fully
# reproducible between hosts, so only x86_64 actually builds it.
%ifarch x86_64
%if 0%{?fedora}
%global cross_targets wasm32-unknown-unknown
%endif
%endif

# Using llvm-static may be helpful as an opt-in, e.g. to aid LLVM rebases.
%bcond_with llvm_static

# We can also choose to just use Rust's bundled LLVM, in case the system LLVM
# is insufficient.  Rust currently requires LLVM 10.0+.
%bcond_with bundled_llvm

# Requires stable libgit2 1.1
%if 0%{?fedora} >= 34
%bcond_with bundled_libgit2
%else
%bcond_without bundled_libgit2
%endif

%if 0%{?rhel}
# Disable cargo->libgit2->libssh2 on RHEL, as it's not approved for FIPS (rhbz1732949)
%bcond_without disabled_libssh2
%else
%bcond_with disabled_libssh2
%endif

%if 0%{?rhel} && 0%{?rhel} < 8
%bcond_with curl_http2
%else
%bcond_without curl_http2
%endif

# LLDB isn't available everywhere...
%if 0%{?rhel} && 0%{?rhel} < 8
%bcond_with lldb
%else
%bcond_without lldb
%endif

Name:           rust
Version:        1.56.0
Release:        1%{?dist}
Summary:        The Rust Programming Language
License:        (ASL 2.0 or MIT) and (BSD and MIT)
# ^ written as: (rust itself) and (bundled libraries)
URL:            https://www.rust-lang.org
ExclusiveArch:  %{rust_arches}

%if "%{channel}" == "stable"
%global rustc_package rustc-%{version}-src
%else
%global rustc_package rustc-%{channel}-src
%endif
Source0:        https://static.rust-lang.org/dist/%{rustc_package}.tar.xz

# An internal rust-abi change broke s390x, but it's fixed in LLVM 12.0.1.
# We'll revert the change on Fedora 33 that has an unpatched LLVM 11.
# https://github.com/rust-lang/rust/issues/80810#issuecomment-781784032
Patch1:         0001-Revert-Auto-merge-of-79547.patch

# By default, rust tries to use "rust-lld" as a linker for WebAssembly.
Patch2:         0001-Use-lld-provided-by-system-for-wasm.patch

### RHEL-specific patches below ###

# Disable cargo->libgit2->libssh2 on RHEL, as it's not approved for FIPS (rhbz1732949)
Patch100:       rustc-1.56.0-disable-libssh2.patch

# libcurl on RHEL7 doesn't have http2, but since cargo requests it, curl-sys
# will try to build it statically -- instead we turn off the feature.
Patch101:       rustc-1.56.0-disable-http2.patch

# kernel rh1410097 causes too-small stacks for PIE.
# (affects RHEL6 kernels when building for RHEL7)
Patch102:       rustc-1.51.0-no-default-pie.patch


# Get the Rust triple for any arch.
%{lua: function rust_triple(arch)
  local abi = "gnu"
  if arch == "armv7hl" then
    arch = "armv7"
    abi = "gnueabihf"
  elseif arch == "ppc64" then
    arch = "powerpc64"
  elseif arch == "ppc64le" then
    arch = "powerpc64le"
  elseif arch == "riscv64" then
    arch = "riscv64gc"
  end
  return arch.."-unknown-linux-"..abi
end}

%global rust_triple %{lua: print(rust_triple(rpm.expand("%{_target_cpu}")))}

%if %defined bootstrap_arches
# For each bootstrap arch, add an additional binary Source.
# Also define bootstrap_source just for the current target.
%{lua: do
  local bootstrap_arches = {}
  for arch in string.gmatch(rpm.expand("%{bootstrap_arches}"), "%S+") do
    table.insert(bootstrap_arches, arch)
  end
  local base = rpm.expand("https://static.rust-lang.org/dist/%{bootstrap_date}"
                          .."/rust-%{bootstrap_channel}")
  local target_arch = rpm.expand("%{_target_cpu}")
  for i, arch in ipairs(bootstrap_arches) do
    print(string.format("Source%d: %s-%s.tar.xz\n",
                        i, base, rust_triple(arch)))
    if arch == target_arch then
      rpm.define("bootstrap_source "..i)
    end
  end
end}
%endif

%ifarch %{bootstrap_arches}
%global bootstrap_root rust-%{bootstrap_channel}-%{rust_triple}
%global local_rust_root %{_builddir}/%{bootstrap_root}/usr
Provides:       bundled(%{name}-bootstrap) = %{bootstrap_rust}
%else
BuildRequires:  cargo >= %{bootstrap_cargo}
%if 0%{?rhel} && 0%{?rhel} < 8
BuildRequires:  %{name} >= %{bootstrap_rust}
BuildConflicts: %{name} > %{version}
%else
BuildRequires:  (%{name} >= %{bootstrap_rust} with %{name} <= %{version})
%endif
%global local_rust_root %{_prefix}
%endif

BuildRequires:  make
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  ncurses-devel
BuildRequires:  curl
# explicit curl-devel to avoid httpd24-curl (rhbz1540167)
BuildRequires:  curl-devel
BuildRequires:  pkgconfig(libcurl)
BuildRequires:  pkgconfig(liblzma)
BuildRequires:  pkgconfig(openssl)
BuildRequires:  pkgconfig(zlib)

%if %without bundled_libgit2
BuildRequires:  pkgconfig(libgit2) >= 1.1.0
%endif

%if %{without disabled_libssh2}
# needs libssh2_userauth_publickey_frommemory
BuildRequires:  pkgconfig(libssh2) >= 1.6.0
%endif

%global python python3
BuildRequires:  %{python}

%if %with bundled_llvm
BuildRequires:  cmake3 >= 3.13.4
BuildRequires:  ninja-build
Provides:       bundled(llvm) = 13.0.0
%else
BuildRequires:  cmake >= 2.8.11
%if 0%{?epel} == 7
%global llvm llvm11
%endif
%if 0%{?fedora} == 35
# f35 still only has 13.0.0~rc1
%global llvm llvm12
%endif
%if %defined llvm
%global llvm_root %{_libdir}/%{llvm}
%else
%global llvm llvm
%global llvm_root %{_prefix}
%endif
BuildRequires:  %{llvm}-devel >= 10.0
%if %with llvm_static
BuildRequires:  %{llvm}-static
BuildRequires:  libffi-devel
%endif
%endif

# make check needs "ps" for src/test/run-pass/wait-forked-but-failed-child.rs
BuildRequires:  procps-ng

# debuginfo-gdb tests need gdb
BuildRequires:  gdb

# Virtual provides for folks who attempt "dnf install rustc"
Provides:       rustc = %{version}-%{release}
Provides:       rustc%{?_isa} = %{version}-%{release}

# Always require our exact standard library
Requires:       %{name}-std-static%{?_isa} = %{version}-%{release}

# The C compiler is needed at runtime just for linking.  Someday rustc might
# invoke the linker directly, and then we'll only need binutils.
# https://github.com/rust-lang/rust/issues/11937
Requires:       /usr/bin/cc

%if 0%{?epel} == 7
%global devtoolset_name devtoolset-9
BuildRequires:  %{devtoolset_name}-gcc
BuildRequires:  %{devtoolset_name}-gcc-c++
%global __cc /opt/rh/%{devtoolset_name}/root/usr/bin/gcc
%global __cxx /opt/rh/%{devtoolset_name}/root/usr/bin/g++
%endif

# ALL Rust libraries are private, because they don't keep an ABI.
%global _privatelibs lib(.*-[[:xdigit:]]{16}*|rustc.*)[.]so.*
%global __provides_exclude ^(%{_privatelibs})$
%global __requires_exclude ^(%{_privatelibs})$
%global __provides_exclude_from ^(%{_docdir}|%{rustlibdir}/src)/.*$
%global __requires_exclude_from ^(%{_docdir}|%{rustlibdir}/src)/.*$

# While we don't want to encourage dynamic linking to Rust shared libraries, as
# there's no stable ABI, we still need the unallocated metadata (.rustc) to
# support custom-derive plugins like #[proc_macro_derive(Foo)].
%if 0%{?rhel} && 0%{?rhel} < 8
# eu-strip is very eager by default, so we have to limit it to -g, only debugging symbols.
%global _find_debuginfo_opts -g
%undefine _include_minidebuginfo
%else
# Newer find-debuginfo.sh supports --keep-section, which is preferable. rhbz1465997
%global _find_debuginfo_opts --keep-section .rustc
%endif

# Use hardening ldflags.
%global rustflags -Clink-arg=-Wl,-z,relro,-z,now

%if %{without bundled_llvm}
%if "%{llvm_root}" == "%{_prefix}" || 0%{?scl:1}
%global llvm_has_filecheck 1
%endif
%endif

# We're going to override --libdir when configuring to get rustlib into a
# common path, but we'll fix the shared libraries during install.
%global common_libdir %{_prefix}/lib
%global rustlibdir %{common_libdir}/rustlib

%if %defined cross_targets
# brp-strip-static-archive breaks the archive index for wasm
%global __os_install_post \
%__os_install_post \
find '%{buildroot}%{rustlibdir}' -type f -path '*/wasm*/lib/*.rlib' -print -exec '%{llvm_root}/bin/llvm-ranlib' '{}' ';' \
%{nil}
%endif

%description
Rust is a systems programming language that runs blazingly fast, prevents
segfaults, and guarantees thread safety.

This package includes the Rust compiler and documentation generator.


%package std-static
Summary:        Standard library for Rust

%description std-static
This package includes the standard libraries for building applications
written in Rust.

%if %defined cross_targets
%{lua: do
  for triple in string.gmatch(rpm.expand("%{cross_targets}"), "%S+") do
    local requires = rpm.expand("Requires: rust = %{version}-%{release}")
    if string.sub(triple, 1, 4) == "wasm" then
      requires = requires .. "\nRequires: lld >= 8.0"
    end
    local subs = {
      triple = triple,
      requires = requires,
    }
    local s = string.gsub([[
%package std-static-{{triple}}
Summary:        Standard library for Rust
BuildArch:      noarch
{{requires}}

%description std-static-{{triple}}
This package includes the standard libraries for building applications
written in Rust for the {{triple}} target.
]], "{{(%w+)}}", subs)
    print(s)
  end
end}
%endif


%package debugger-common
Summary:        Common debugger pretty printers for Rust
BuildArch:      noarch

%description debugger-common
This package includes the common functionality for %{name}-gdb and %{name}-lldb.


%package gdb
Summary:        GDB pretty printers for Rust
BuildArch:      noarch
Requires:       gdb
Requires:       %{name}-debugger-common = %{version}-%{release}

%description gdb
This package includes the rust-gdb script, which allows easier debugging of Rust
programs.


%if %with lldb

%package lldb
Summary:        LLDB pretty printers for Rust
BuildArch:      noarch
Requires:       lldb
Requires:       %{python}-lldb
Requires:       %{name}-debugger-common = %{version}-%{release}

%description lldb
This package includes the rust-lldb script, which allows easier debugging of Rust
programs.

%endif


%package doc
Summary:        Documentation for Rust
# NOT BuildArch:      noarch
# Note, while docs are mostly noarch, some things do vary by target_arch.
# Koji will fail the build in rpmdiff if two architectures build a noarch
# subpackage differently, so instead we have to keep its arch.

%description doc
This package includes HTML documentation for the Rust programming language and
its standard library.


%package -n cargo
Summary:        Rust's package manager and build tool
%if %with bundled_libgit2
Provides:       bundled(libgit2) = 1.1.0
%endif
# For tests:
BuildRequires:  git
# Cargo is not much use without Rust
Requires:       rust

# "cargo vendor" is a builtin command starting with 1.37.  The Obsoletes and
# Provides are mostly relevant to RHEL, but harmless to have on Fedora/etc. too
Obsoletes:      cargo-vendor <= 0.1.23
Provides:       cargo-vendor = %{version}-%{release}

%description -n cargo
Cargo is a tool that allows Rust projects to declare their various dependencies
and ensure that you'll always get a repeatable build.


%package -n cargo-doc
Summary:        Documentation for Cargo
BuildArch:      noarch
# Cargo no longer builds its own documentation
# https://github.com/rust-lang/cargo/pull/4904
Requires:       rust-doc = %{version}-%{release}

%description -n cargo-doc
This package includes HTML documentation for Cargo.


%package -n rustfmt
Summary:        Tool to find and fix Rust formatting issues
Requires:       cargo

# The component/package was rustfmt-preview until Rust 1.31.
Obsoletes:      rustfmt-preview < 1.0.0
Provides:       rustfmt-preview = %{version}-%{release}

%description -n rustfmt
A tool for formatting Rust code according to style guidelines.


%package -n rls
Summary:        Rust Language Server for IDE integration
%if %with bundled_libgit2
Provides:       bundled(libgit2) = 1.1.0
%endif
Requires:       rust-analysis
# /usr/bin/rls is dynamically linked against internal rustc libs
Requires:       %{name}%{?_isa} = %{version}-%{release}

# The component/package was rls-preview until Rust 1.31.
Obsoletes:      rls-preview < 1.31.6
Provides:       rls-preview = %{version}-%{release}

%description -n rls
The Rust Language Server provides a server that runs in the background,
providing IDEs, editors, and other tools with information about Rust programs.
It supports functionality such as 'goto definition', symbol search,
reformatting, and code completion, and enables renaming and refactorings.


%package -n clippy
Summary:        Lints to catch common mistakes and improve your Rust code
Requires:       cargo
# /usr/bin/clippy-driver is dynamically linked against internal rustc libs
Requires:       %{name}%{?_isa} = %{version}-%{release}

# The component/package was clippy-preview until Rust 1.31.
Obsoletes:      clippy-preview <= 0.0.212
Provides:       clippy-preview = %{version}-%{release}

%description -n clippy
A collection of lints to catch common mistakes and improve your Rust code.


%package src
Summary:        Sources for the Rust standard library
BuildArch:      noarch

%description src
This package includes source files for the Rust standard library.  It may be
useful as a reference for code completion tools in various editors.


%package analysis
Summary:        Compiler analysis data for the Rust standard library
Requires:       rust-std-static%{?_isa} = %{version}-%{release}

%description analysis
This package contains analysis data files produced with rustc's -Zsave-analysis
feature for the Rust standard library. The RLS (Rust Language Server) uses this
data to provide information about the Rust standard library.


%prep

%ifarch %{bootstrap_arches}
%setup -q -n %{bootstrap_root} -T -b %{bootstrap_source}
./install.sh --components=cargo,rustc,rust-std-%{rust_triple} \
  --prefix=%{local_rust_root} --disable-ldconfig
test -f '%{local_rust_root}/bin/cargo'
test -f '%{local_rust_root}/bin/rustc'
%endif

%setup -q -n %{rustc_package}

%if 0%{?fedora} == 33
# revert only for LLVM 11
%patch1 -p1
%endif

%patch2 -p1

%if %with disabled_libssh2
%patch100 -p1
%endif

%if %without curl_http2
%patch101 -p1
rm -rf vendor/libnghttp2-sys/
%endif

%if 0%{?rhel} && 0%{?rhel} < 8
%patch102 -p1
%endif

%if "%{python}" != "python3"
# Use our preferred python first
sed -i.try-python -e '/^try python3 /i try "%{python}" "$@"' ./configure
%endif

%if %without bundled_llvm
rm -rf src/llvm-project/
mkdir -p src/llvm-project/libunwind/
%endif

# Remove other unused vendored libraries
rm -rf vendor/curl-sys/curl/
rm -rf vendor/jemalloc-sys/jemalloc/
rm -rf vendor/libssh2-sys/libssh2/
rm -rf vendor/libz-sys/src/zlib/
rm -rf vendor/libz-sys/src/zlib-ng/
rm -rf vendor/lzma-sys/xz-*/
rm -rf vendor/openssl-src/openssl/

%if %without bundled_libgit2
rm -rf vendor/libgit2-sys/libgit2/
%endif

%if %with disabled_libssh2
rm -rf vendor/libssh2-sys/
%endif

# This only affects the transient rust-installer, but let it use our dynamic xz-libs
sed -i.lzma -e '/LZMA_API_STATIC/d' src/bootstrap/tool.rs

%if %{with bundled_llvm} && 0%{?epel} == 7
mkdir -p cmake-bin
ln -s /usr/bin/cmake3 cmake-bin/cmake
%global cmake_path $PWD/cmake-bin
%endif

%if %{without bundled_llvm} && %{with llvm_static}
# Static linking to distro LLVM needs to add -lffi
# https://github.com/rust-lang/rust/issues/34486
sed -i.ffi -e '$a #[link(name = "ffi")] extern {}' \
  src/librustc_llvm/lib.rs
%endif

# The configure macro will modify some autoconf-related files, which upsets
# cargo when it tries to verify checksums in those files.  If we just truncate
# that file list, cargo won't have anything to complain about.
find vendor -name .cargo-checksum.json \
  -exec sed -i.uncheck -e 's/"files":{[^}]*}/"files":{ }/' '{}' '+'

# Sometimes Rust sources start with #![...] attributes, and "smart" editors think
# it's a shebang and make them executable. Then brp-mangle-shebangs gets upset...
find -name '*.rs' -type f -perm /111 -exec chmod -v -x '{}' '+'

# Set up shared environment variables for build/install/check
%global rust_env RUSTFLAGS="%{rustflags}"
%if 0%{?cmake_path:1}
%global rust_env %{rust_env} PATH="%{cmake_path}:$PATH"
%endif
%if %without bundled_libgit2
# convince libgit2-sys to use the distro libgit2
%global rust_env %{rust_env} LIBGIT2_SYS_USE_PKG_CONFIG=1
%endif
%if %without disabled_libssh2
# convince libssh2-sys to use the distro libssh2
%global rust_env %{rust_env} LIBSSH2_SYS_USE_PKG_CONFIG=1
%endif


%build
export %{rust_env}

%ifarch %{arm} %{ix86} s390x
# full debuginfo is exhausting memory; just do libstd for now
# https://github.com/rust-lang/rust/issues/45854
%if 0%{?rhel} && 0%{?rhel} < 8
# Older rpmbuild didn't work with partial debuginfo coverage.
%global debug_package %{nil}
%define enable_debuginfo --debuginfo-level=0
%else
%define enable_debuginfo --debuginfo-level=0 --debuginfo-level-std=2
%endif
%else
%define enable_debuginfo --debuginfo-level=2
%endif

# Some builders have relatively little memory for their CPU count.
# At least 2GB per CPU is a good rule of thumb for building rustc.
ncpus=$(/usr/bin/getconf _NPROCESSORS_ONLN)
max_cpus=$(( ($(free -g | awk '/^Mem:/{print $2}') + 1) / 2 ))
if [ "$max_cpus" -ge 1 -a "$max_cpus" -lt "$ncpus" ]; then
  ncpus="$max_cpus"
fi

%configure --disable-option-checking \
  --libdir=%{common_libdir} \
  --build=%{rust_triple} --host=%{rust_triple} --target=%{rust_triple} \
  --set target.%{rust_triple}.linker=%{__cc} \
  --set target.%{rust_triple}.cc=%{__cc} \
  --set target.%{rust_triple}.cxx=%{__cxx} \
  --python=%{python} \
  --local-rust-root=%{local_rust_root} \
  %{!?with_bundled_llvm: --llvm-root=%{llvm_root} \
    %{!?llvm_has_filecheck: --disable-codegen-tests} \
    %{!?with_llvm_static: --enable-llvm-link-shared } } \
  --disable-rpath \
  %{enable_debuginfo} \
  --set rust.codegen-units-std=1 \
  --enable-extended \
  --tools=analysis,cargo,clippy,rls,rustfmt,src \
  --enable-vendor \
  --enable-verbose-tests \
  %{?codegen_units_std} \
  --dist-compression-formats=gz \
  --release-channel=%{channel} \
  --release-description="%{?fedora:Fedora }%{?rhel:Red Hat }%{version}-%{release}"

%{python} ./x.py build -j "$ncpus" --stage 2
%{python} ./x.py doc --stage 2

%if %defined cross_targets
for triple in %{cross_targets}; do
  %{python} ./x.py build --stage 2 --target=$triple std
done
%endif

%install
export %{rust_env}

DESTDIR=%{buildroot} %{python} ./x.py install

%if %defined cross_targets
for triple in %{cross_targets}; do
  DESTDIR=%{buildroot} %{python} ./x.py install --target=$triple std
done
%endif

# These are transient files used by x.py dist and install
rm -rf ./build/dist/ ./build/tmp/

# Make sure the shared libraries are in the proper libdir
%if "%{_libdir}" != "%{common_libdir}"
mkdir -p %{buildroot}%{_libdir}
find %{buildroot}%{common_libdir} -maxdepth 1 -type f -name '*.so' \
  -exec mv -v -t %{buildroot}%{_libdir} '{}' '+'
%endif

# The shared libraries should be executable for debuginfo extraction.
find %{buildroot}%{_libdir} -maxdepth 1 -type f -name '*.so' \
  -exec chmod -v +x '{}' '+'

# The libdir libraries are identical to those under rustlib/.  It's easier on
# library loading if we keep them in libdir, but we do need them in rustlib/
# to support dynamic linking for compiler plugins, so we'll symlink.
(cd "%{buildroot}%{rustlibdir}/%{rust_triple}/lib" &&
 find ../../../../%{_lib} -maxdepth 1 -name '*.so' |
 while read lib; do
   if [ -f "${lib##*/}" ]; then
     # make sure they're actually identical!
     cmp "$lib" "${lib##*/}"
     ln -v -f -s -t . "$lib"
   fi
 done)

# Remove installer artifacts (manifests, uninstall scripts, etc.)
find %{buildroot}%{rustlibdir} -maxdepth 1 -type f -exec rm -v '{}' '+'

# Remove backup files from %%configure munging
find %{buildroot}%{rustlibdir} -type f -name '*.orig' -exec rm -v '{}' '+'

# https://fedoraproject.org/wiki/Changes/Make_ambiguous_python_shebangs_error
# We don't actually need to ship any of those python scripts in rust-src anyway.
find %{buildroot}%{rustlibdir}/src -type f -name '*.py' -exec rm -v '{}' '+'

# FIXME: __os_install_post will strip the rlibs
# -- should we find a way to preserve debuginfo?

# Remove unwanted documentation files (we already package them)
rm -f %{buildroot}%{_docdir}/%{name}/README.md
rm -f %{buildroot}%{_docdir}/%{name}/COPYRIGHT
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE-APACHE
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE-MIT
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE-THIRD-PARTY
rm -f %{buildroot}%{_docdir}/%{name}/*.old

# Sanitize the HTML documentation
find %{buildroot}%{_docdir}/%{name}/html -empty -delete
find %{buildroot}%{_docdir}/%{name}/html -type f -exec chmod -x '{}' '+'

# Create the path for crate-devel packages
mkdir -p %{buildroot}%{_datadir}/cargo/registry

# Cargo no longer builds its own documentation
# https://github.com/rust-lang/cargo/pull/4904
mkdir -p %{buildroot}%{_docdir}/cargo
ln -sT ../rust/html/cargo/ %{buildroot}%{_docdir}/cargo/html

%if %without lldb
rm -f %{buildroot}%{_bindir}/rust-lldb
rm -f %{buildroot}%{rustlibdir}/etc/lldb_*
%endif

# We don't want Rust copies of LLVM tools (rust-lld, rust-llvm-dwp)
rm -f %{buildroot}%{rustlibdir}/%{rust_triple}/bin/rust-ll*


%check
export %{rust_env}

# The results are not stable on koji, so mask errors and just log it.
# Some of the larger test artifacts are manually cleaned to save space.
%{python} ./x.py test --no-fail-fast --stage 2 || :
rm -rf "./build/%{rust_triple}/test/"

%{python} ./x.py test --no-fail-fast --stage 2 cargo || :
rm -rf "./build/%{rust_triple}/stage2-tools/%{rust_triple}/cit/"

%{python} ./x.py test --no-fail-fast --stage 2 clippy || :

env RLS_TEST_WAIT_FOR_AGES=1 \
%{python} ./x.py test --no-fail-fast --stage 2 rls || :

%{python} ./x.py test --no-fail-fast --stage 2 rustfmt || :


%ldconfig_scriptlets


%files
%license COPYRIGHT LICENSE-APACHE LICENSE-MIT
%doc README.md
%{_bindir}/rustc
%{_bindir}/rustdoc
%{_libdir}/*.so
%{_mandir}/man1/rustc.1*
%{_mandir}/man1/rustdoc.1*
%dir %{rustlibdir}
%dir %{rustlibdir}/%{rust_triple}
%dir %{rustlibdir}/%{rust_triple}/lib
%{rustlibdir}/%{rust_triple}/lib/*.so


%files std-static
%dir %{rustlibdir}
%dir %{rustlibdir}/%{rust_triple}
%dir %{rustlibdir}/%{rust_triple}/lib
%{rustlibdir}/%{rust_triple}/lib/*.rlib


%if %defined cross_targets
%{lua: do
  for triple in string.gmatch(rpm.expand("%{cross_targets}"), "%S+") do
    local subs = {
      triple = triple,
      rustlibdir = rpm.expand("%{rustlibdir}"),
    }
    local s = string.gsub([[
%files std-static-{{triple}}
%dir {{rustlibdir}}
%dir {{rustlibdir}}/{{triple}}
%dir {{rustlibdir}}/{{triple}}/lib
{{rustlibdir}}/{{triple}}/lib/*.rlib
]], "{{(%w+)}}", subs)
    print(s)
  end
end}
%endif


%files debugger-common
%dir %{rustlibdir}
%dir %{rustlibdir}/etc
%{rustlibdir}/etc/rust_*.py*


%files gdb
%{_bindir}/rust-gdb
%{rustlibdir}/etc/gdb_*
%exclude %{_bindir}/rust-gdbgui


%if %with lldb
%files lldb
%{_bindir}/rust-lldb
%{rustlibdir}/etc/lldb_*
%endif


%files doc
%docdir %{_docdir}/%{name}
%dir %{_docdir}/%{name}
%dir %{_docdir}/%{name}/html
%{_docdir}/%{name}/html/*/
%{_docdir}/%{name}/html/*.html
%{_docdir}/%{name}/html/*.css
%{_docdir}/%{name}/html/*.js
%{_docdir}/%{name}/html/*.png
%{_docdir}/%{name}/html/*.svg
%{_docdir}/%{name}/html/*.woff
%{_docdir}/%{name}/html/*.woff2
%license %{_docdir}/%{name}/html/*.txt
%license %{_docdir}/%{name}/html/*.md


%files -n cargo
%license src/tools/cargo/LICENSE-APACHE src/tools/cargo/LICENSE-MIT src/tools/cargo/LICENSE-THIRD-PARTY
%doc src/tools/cargo/README.md
%{_bindir}/cargo
%{_libexecdir}/cargo*
%{_mandir}/man1/cargo*.1*
%{_sysconfdir}/bash_completion.d/cargo
%{_datadir}/zsh/site-functions/_cargo
%dir %{_datadir}/cargo
%dir %{_datadir}/cargo/registry


%files -n cargo-doc
%docdir %{_docdir}/cargo
%dir %{_docdir}/cargo
%{_docdir}/cargo/html


%files -n rustfmt
%{_bindir}/rustfmt
%{_bindir}/cargo-fmt
%doc src/tools/rustfmt/{README,CHANGELOG,Configurations}.md
%license src/tools/rustfmt/LICENSE-{APACHE,MIT}


%files -n rls
%{_bindir}/rls
%doc src/tools/rls/{README.md,COPYRIGHT,debugging.md}
%license src/tools/rls/LICENSE-{APACHE,MIT}


%files -n clippy
%{_bindir}/cargo-clippy
%{_bindir}/clippy-driver
%doc src/tools/clippy/{README.md,CHANGELOG.md}
%license src/tools/clippy/LICENSE-{APACHE,MIT}


%files src
%dir %{rustlibdir}
%{rustlibdir}/src


%files analysis
%{rustlibdir}/%{rust_triple}/analysis/


%changelog
* Thu Oct 21 2021 Josh Stone <jistone@redhat.com> - 1.56.0-1
- Update to 1.56.0.

* Tue Sep 14 2021 Sahana Prasad <sahana@redhat.com> - 1.55.0-2
- Rebuilt with OpenSSL 3.0.0

* Thu Sep 09 2021 Josh Stone <jistone@redhat.com> - 1.55.0-1
- Update to 1.55.0.
- Use llvm-ranlib for wasm rlibs; Fixes rhbz#2002612

* Tue Aug 24 2021 Josh Stone <jistone@redhat.com> - 1.54.0-2
- Build with LLVM 12 on Fedora 35+

* Thu Jul 29 2021 Josh Stone <jistone@redhat.com> - 1.54.0-1
- Update to 1.54.0.

* Fri Jul 23 2021 Fedora Release Engineering <releng@fedoraproject.org> - 1.53.0-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_35_Mass_Rebuild

* Thu Jul 08 2021 Josh Stone <jistone@redhat.com> - 1.53.0-2
- Exclude wasm on s390x for lack of lld

* Thu Jun 17 2021 Josh Stone <jistone@redhat.com> - 1.53.0-1
- Update to 1.53.0.

* Wed Jun 02 2021 Josh Stone <jistone@redhat.com> - 1.52.1-2
- Set rust.codegen-units-std=1 for all targets again.
- Add rust-std-static-wasm32-unknown-unknown.
- Rebuild f34 with LLVM 12.

* Mon May 10 2021 Josh Stone <jistone@redhat.com> - 1.52.1-1
- Update to 1.52.1.

* Thu May 06 2021 Josh Stone <jistone@redhat.com> - 1.52.0-1
- Update to 1.52.0.

* Fri Apr 16 2021 Josh Stone <jistone@redhat.com> - 1.51.0-3
- Security fixes for CVE-2020-36323, CVE-2021-31162

* Wed Apr 14 2021 Josh Stone <jistone@redhat.com> - 1.51.0-2
- Security fixes for CVE-2021-28876, CVE-2021-28878, CVE-2021-28879
- Fix bootstrap for stage0 rust 1.51

* Thu Mar 25 2021 Josh Stone <jistone@redhat.com> - 1.51.0-1
- Update to 1.51.0.

* Thu Feb 11 2021 Josh Stone <jistone@redhat.com> - 1.50.0-1
- Update to 1.50.0.

* Wed Jan 27 2021 Fedora Release Engineering <releng@fedoraproject.org> - 1.49.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_34_Mass_Rebuild

* Tue Jan 05 2021 Josh Stone <jistone@redhat.com> - 1.49.0-1
- Update to 1.49.0.

* Tue Dec 29 2020 Igor Raits <ignatenkobrain@fedoraproject.org> - 1.48.0-3
- De-bootstrap

* Mon Dec 28 2020 Igor Raits <ignatenkobrain@fedoraproject.org> - 1.48.0-2
- Rebuild for libgit2 1.1.x

* Thu Nov 19 2020 Josh Stone <jistone@redhat.com> - 1.48.0-1
- Update to 1.48.0.

* Sat Oct 10 2020 Jeff Law <law@redhat.com> - 1.47.0-2
- Re-enable LTO

* Thu Oct 08 2020 Josh Stone <jistone@redhat.com> - 1.47.0-1
- Update to 1.47.0.

* Fri Aug 28 2020 Fabio Valentini <decathorpe@gmail.com> - 1.46.0-2
- Fix LTO with doctests (backported cargo PR#8657).

* Thu Aug 27 2020 Josh Stone <jistone@redhat.com> - 1.46.0-1
- Update to 1.46.0.

* Mon Aug 03 2020 Josh Stone <jistone@redhat.com> - 1.45.2-1
- Update to 1.45.2.

* Thu Jul 30 2020 Josh Stone <jistone@redhat.com> - 1.45.1-1
- Update to 1.45.1.

* Wed Jul 29 2020 Fedora Release Engineering <releng@fedoraproject.org> - 1.45.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Thu Jul 16 2020 Josh Stone <jistone@redhat.com> - 1.45.0-1
- Update to 1.45.0.

* Wed Jul 01 2020 Jeff Law <law@redhat.com> - 1.44.1-2
- Disable LTO

* Thu Jun 18 2020 Josh Stone <jistone@redhat.com> - 1.44.1-1
- Update to 1.44.1.

* Thu Jun 04 2020 Josh Stone <jistone@redhat.com> - 1.44.0-1
- Update to 1.44.0.

* Tue May 19 2020 Josh Stone <jistone@redhat.com> - 1.43.1-1.1
- Rebuild with LLVM 9.

* Thu May 07 2020 Josh Stone <jistone@redhat.com> - 1.43.1-1
- Update to 1.43.1.

* Thu Apr 23 2020 Josh Stone <jistone@redhat.com> - 1.43.0-1
- Update to 1.43.0.

* Thu Mar 12 2020 Josh Stone <jistone@redhat.com> - 1.42.0-1
- Update to 1.42.0.

* Thu Feb 27 2020 Josh Stone <jistone@redhat.com> - 1.41.1-1
- Update to 1.41.1.

* Thu Feb 20 2020 Josh Stone <jistone@redhat.com> - 1.41.0-2
- Rebuild with llvm9.0

* Thu Jan 30 2020 Josh Stone <jistone@redhat.com> - 1.41.0-1
- Update to 1.41.0.

* Thu Jan 16 2020 Josh Stone <jistone@redhat.com> - 1.40.0-3
- Build compiletest with in-tree libtest

* Tue Jan 07 2020 Josh Stone <jistone@redhat.com> - 1.40.0-2
- Fix compiletest with newer (local-rebuild) libtest
- Fix ARM EHABI unwinding

* Thu Dec 19 2019 Josh Stone <jistone@redhat.com> - 1.40.0-1
- Update to 1.40.0.

* Tue Nov 12 2019 Josh Stone <jistone@redhat.com> - 1.39.0-2
- Fix a couple build and test issues with rustdoc.

* Thu Nov 07 2019 Josh Stone <jistone@redhat.com> - 1.39.0-1
- Update to 1.39.0.

* Fri Sep 27 2019 Josh Stone <jistone@redhat.com> - 1.38.0-2
- Filter the libraries included in rust-std (rhbz1756487)

* Thu Sep 26 2019 Josh Stone <jistone@redhat.com> - 1.38.0-1
- Update to 1.38.0.

* Thu Aug 15 2019 Josh Stone <jistone@redhat.com> - 1.37.0-1
- Update to 1.37.0.
- Disable HTTP/2 support, lacking in system libcurl.

* Fri Jul 26 2019 Fedora Release Engineering <releng@fedoraproject.org> - 1.36.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_31_Mass_Rebuild

* Thu Jul 04 2019 Josh Stone <jistone@redhat.com> - 1.36.0-1
- Update to 1.36.0.

* Wed May 29 2019 Josh Stone <jistone@redhat.com> - 1.35.0-2
- Fix compiletest for rebuild testing.

* Thu May 23 2019 Josh Stone <jistone@redhat.com> - 1.35.0-1
- Update to 1.35.0.

* Tue May 14 2019 Josh Stone <jistone@redhat.com> - 1.34.2-1
- Update to 1.34.2 -- fixes CVE-2019-12083.

* Thu Apr 25 2019 Josh Stone <jistone@redhat.com> - 1.34.1-1
- Update to 1.34.1.
- Add a ThinLTO fix for rhbz1701339.

* Thu Apr 11 2019 Josh Stone <jistone@redhat.com> - 1.34.0-1
- Update to 1.34.0.

* Fri Mar 01 2019 Josh Stone <jistone@redhat.com> - 1.33.0-2
- Fix deprecations for self-rebuild

* Thu Feb 28 2019 Josh Stone <jistone@redhat.com> - 1.33.0-1
- Update to 1.33.0.

* Sat Feb 02 2019 Fedora Release Engineering <releng@fedoraproject.org> - 1.32.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Thu Jan 17 2019 Josh Stone <jistone@redhat.com> - 1.32.0-1
- Update to 1.32.0.

* Mon Jan 07 2019 Josh Stone <jistone@redhat.com> - 1.31.1-9
- Update to 1.31.1 for RLS fixes.

* Thu Dec 06 2018 Josh Stone <jistone@redhat.com> - 1.31.0-8
- Update to 1.31.0 -- Rust 2018!
- clippy/rls/rustfmt are no longer -preview

* Thu Nov 08 2018 Josh Stone <jistone@redhat.com> - 1.30.1-7
- Update to 1.30.1.

* Thu Nov 01 2018 Josh Stone <jistone@redhat.com> - 1.30.0-6.1
- Rebuild without bootstrap binaries.

* Thu Oct 25 2018 Josh Stone <jistone@redhat.com> - 1.30.0-6
- Update to 1.30.0.
- Re-bootstrap ppc64le for rust#54545

* Fri Oct 12 2018 Josh Stone <jistone@redhat.com> - 1.29.2-3
- Update to 1.29.2.

* Tue Sep 25 2018 Josh Stone <jistone@redhat.com> - 1.29.1-2
- Update to 1.29.1.
- Security fix for str::repeat (pending CVE).

* Thu Sep 13 2018 Josh Stone <jistone@redhat.com> - 1.29.0-1
- Update to 1.29.0.
- Add a clippy-preview subpackage

* Wed Aug 08 2018 Josh Stone <jistone@redhat.com> - 1.28.0-1
- Update to 1.28.0.

* Tue Jul 24 2018 Josh Stone <jistone@redhat.com> - 1.27.2-3
- Update to 1.27.2.

* Tue Jul 10 2018 Josh Stone <jistone@redhat.com> - 1.27.1-2
- Update to 1.27.1.
- Security fix for CVE-2018-1000622

* Thu Jun 21 2018 Josh Stone <jistone@redhat.com> - 1.27.0-1
- Update to 1.27.0.

* Wed Jun 06 2018 Josh Stone <jistone@redhat.com> - 1.26.2-3
- Update to 1.26.2.

* Tue May 29 2018 Josh Stone <jistone@redhat.com> - 1.26.1-2
- Update to 1.26.1.

* Thu May 10 2018 Josh Stone <jistone@redhat.com> - 1.26.0-1
- Update to 1.26.0.

* Mon Apr 16 2018 Dan Callaghan <dcallagh@redhat.com> - 1.25.0-3
- Add cargo, rls, and analysis

* Tue Apr 10 2018 Josh Stone <jistone@redhat.com> - 1.25.0-2
- Filter codegen-backends from Provides too.

* Thu Mar 29 2018 Josh Stone <jistone@redhat.com> - 1.25.0-1
- Update to 1.25.0.

* Thu Mar 01 2018 Josh Stone <jistone@redhat.com> - 1.24.1-1
- Update to 1.24.1.

* Wed Feb 21 2018 Josh Stone <jistone@redhat.com> - 1.24.0-3
- Backport a rebuild fix for rust#48308.

* Mon Feb 19 2018 Josh Stone <jistone@redhat.com> - 1.24.0-2
- rhbz1546541: drop full-bootstrap; cmp libs before symlinking.
- Backport pr46592 to fix local_rebuild bootstrapping.
- Backport pr48362 to fix relative/absolute libdir.

* Thu Feb 15 2018 Josh Stone <jistone@redhat.com> - 1.24.0-1
- Update to 1.24.0.

* Mon Feb 12 2018 Iryna Shcherbina <ishcherb@redhat.com> - 1.23.0-4
- Update Python 2 dependency declarations to new packaging standards
  (See https://fedoraproject.org/wiki/FinalizingFedoraSwitchtoPython3)

* Tue Feb 06 2018 Josh Stone <jistone@redhat.com> - 1.23.0-3
- Use full-bootstrap to work around a rebuild issue.
- Patch binaryen for GCC 8

* Thu Feb 01 2018 Igor Gnatenko <ignatenkobrain@fedoraproject.org> - 1.23.0-2
- Switch to %%ldconfig_scriptlets

* Mon Jan 08 2018 Josh Stone <jistone@redhat.com> - 1.23.0-1
- Update to 1.23.0.

* Thu Nov 23 2017 Josh Stone <jistone@redhat.com> - 1.22.1-1
- Update to 1.22.1.

* Thu Oct 12 2017 Josh Stone <jistone@redhat.com> - 1.21.0-1
- Update to 1.21.0.

* Mon Sep 11 2017 Josh Stone <jistone@redhat.com> - 1.20.0-2
- ABI fixes for ppc64 and s390x.

* Thu Aug 31 2017 Josh Stone <jistone@redhat.com> - 1.20.0-1
- Update to 1.20.0.
- Add a rust-src subpackage.

* Thu Jul 20 2017 Josh Stone <jistone@redhat.com> - 1.19.0-1
- Update to 1.19.0.

* Thu Jun 08 2017 Josh Stone <jistone@redhat.com> - 1.18.0-1
- Update to 1.18.0.

* Mon May 08 2017 Josh Stone <jistone@redhat.com> - 1.17.0-2
- Move shared libraries back to libdir and symlink in rustlib

* Thu Apr 27 2017 Josh Stone <jistone@redhat.com> - 1.17.0-1
- Update to 1.17.0.

* Thu Mar 16 2017 Josh Stone <jistone@redhat.com> - 1.16.0-1
- Update to 1.16.0.
- Use rustbuild instead of the old makefiles.
- Update bootstrapping to include rust-std and cargo.
- Add a rust-lldb subpackage.

* Fri Feb 10 2017 Josh Stone <jistone@redhat.com> - 1.15.1-2
- Rebuild without bootstrap binaries.

* Fri Feb 10 2017 Josh Stone <jistone@redhat.com> - 1.15.1-1
- Update to 1.15.1.
- Require rust-rpm-macros for new crate packaging.
- Keep shared libraries under rustlib/, only debug-stripped.
- Merge and clean up conditionals for epel7.
- Bootstrap ppc64 and ppc64le.

* Tue Jan 03 2017 Josh Stone <jistone@redhat.com> - 1.14.0-1
- Update to 1.14.0.
- Rewrite bootstrap logic to target specific arches.

* Thu Nov 10 2016 Josh Stone <jistone@redhat.com> - 1.13.0-1
- Update to 1.13.0.
- Use hardening flags for linking.
- Split the standard library into its own package
- Centralize rustlib/ under /usr/lib/ for multilib integration.

* Sat Oct 22 2016 Josh Stone <jistone@redhat.com> - 1.12.1-1.1
- Rebuild without bootstrap binaries.

* Sat Oct 22 2016 Josh Stone <jistone@redhat.com> - 1.12.1-1
- Update to 1.12.1.
- Merge package changes from rawhide.
- Bootstrap aarch64.

* Tue Sep 20 2016 Josh Stone <jistone@redhat.com> - 1.11.0-3.2
- Rebuild without bootstrap binaries.

* Mon Sep 19 2016 Josh Stone <jistone@redhat.com> - 1.11.0-3.1
- Bootstrap el7, with bundled llvm

* Sat Sep 03 2016 Josh Stone <jistone@redhat.com> - 1.11.0-3
- Rebuild without bootstrap binaries.

* Fri Sep 02 2016 Josh Stone <jistone@redhat.com> - 1.11.0-2
- Bootstrap armv7hl, with backported no-neon patch.

* Wed Aug 24 2016 Josh Stone <jistone@redhat.com> - 1.11.0-1
- Update to 1.11.0.
- Drop the backported patches.
- Patch get-stage0.py to trust existing bootstrap binaries.
- Use libclang_rt.builtins from compiler-rt, dodging llvm-static issues.
- Use --local-rust-root to make sure the right bootstrap is used.

* Sat Aug 13 2016 Josh Stone <jistone@redhat.com> 1.10.0-4
- Rebuild without bootstrap binaries.

* Fri Aug 12 2016 Josh Stone <jistone@redhat.com> - 1.10.0-3
- Initial import into Fedora (#1356907), bootstrapped
- Format license text as suggested in review.
- Note how the tests already run in parallel.
- Undefine _include_minidebuginfo, because it duplicates ".note.rustc".
- Don't let checks fail the whole build.
- Note that -doc can't be noarch, as rpmdiff doesn't allow variations.

* Tue Jul 26 2016 Josh Stone <jistone@redhat.com> - 1.10.0-2
- Update -doc directory ownership, and mark its licenses.
- Package and declare licenses for libbacktrace and hoedown.
- Set bootstrap_base as a global.
- Explicitly require python2.

* Thu Jul 14 2016 Josh Stone <jistone@fedoraproject.org> - 1.10.0-1
- Initial package, bootstrapped
