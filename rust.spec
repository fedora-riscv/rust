# The channel can be stable, beta, or nightly
%{!?channel: %global channel stable}

# To bootstrap from scratch, set the channel and date from src/stage0.txt
# e.g. 1.10.0 wants rustc: 1.9.0-2016-05-24
# or nightly wants some beta-YYYY-MM-DD
%bcond_with bootstrap
%global bootstrap_channel 1.11.0
%global bootstrap_date 2016-08-16

# We generally don't want llvm-static present at all, since llvm-config will
# make us link statically.  But we can opt in, e.g. to aid LLVM rebases.
%bcond_with llvm_static

%if 0%{?rhel}
%global _with_bundled_llvm 1
%endif
%bcond_with bundled_llvm


# Rust 1.12 metadata is now unallocated data (.rustc), and in theory it should
# be fine to strip this entirely, since we don't want to expose Rust's unstable
# ABI for linking.  However, eu-strip was then clobbering .dynsym when it tried
# to remove the rust_metadata symbol referencing .rustc (rhbz1380961).
# So for unfixed elfutils, we'll leave .rustc alone and only strip debuginfo.
%if 0%{?fedora} < 25
%global _find_debuginfo_opts -g
%undefine _include_minidebuginfo
%endif

Name:           rust
Version:        1.12.1
Release:        1%{?dist}.1
Summary:        The Rust Programming Language
License:        (ASL 2.0 or MIT) and (BSD and ISC and MIT)
# ^ written as: (rust itself) and (bundled libraries)
URL:            https://www.rust-lang.org

%if "%{channel}" == "stable"
%global rustc_package rustc-%{version}
%else
%global rustc_package rustc-%{channel}
%endif
Source0:        https://static.rust-lang.org/dist/%{rustc_package}-src.tar.gz

%if %with bootstrap
%global bootstrap_base https://static.rust-lang.org/dist/%{bootstrap_date}/rustc-%{bootstrap_channel}
Source1:        %{bootstrap_base}-x86_64-unknown-linux-gnu.tar.gz
Source2:        %{bootstrap_base}-i686-unknown-linux-gnu.tar.gz
Source3:        %{bootstrap_base}-armv7-unknown-linux-gnueabihf.tar.gz
Source4:        %{bootstrap_base}-aarch64-unknown-linux-gnu.tar.gz
%endif

# Only x86_64 and i686 are Tier 1 platforms at this time.
# https://doc.rust-lang.org/stable/book/getting-started.html#tier-1
ExclusiveArch:  x86_64 i686 armv7hl aarch64
%ifarch armv7hl
%global rust_triple armv7-unknown-linux-gnueabihf
%else
%global rust_triple %{_target_cpu}-unknown-linux-gnu
%endif

# merged for 1.13.0
Patch1:         rust-pr35814-armv7-no-neon.patch

# merged for 1.14.0
Patch2:         rust-pr36933-less-neon-again.patch

%if 0%{?rhel}
BuildRequires:  cmake3
%else
BuildRequires:  cmake
%endif

BuildRequires:  make
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  ncurses-devel
BuildRequires:  zlib-devel
BuildRequires:  python2
BuildRequires:  curl

%if %with llvm_static
BuildRequires:  llvm-static
BuildRequires:  libffi-devel
%else
# Make sure llvm-config doesn't see it.
BuildConflicts: llvm-static
%endif

%if %with bundled_llvm
Provides:       bundled(llvm) = 3.8
%else
BuildRequires:  llvm-devel
%endif


%if %without bootstrap
BuildRequires:  %{name} <= %{version}
BuildRequires:  %{name} >= %{bootstrap_channel}
%global local_rust_root %{_prefix}
%else
%global bootstrap_root rustc-%{bootstrap_channel}-%{rust_triple}
%global local_rust_root %{_builddir}/%{rustc_package}/%{bootstrap_root}/rustc
%endif

# make check needs "ps" for src/test/run-pass/wait-forked-but-failed-child.rs
BuildRequires:  procps-ng

# TODO: work on unbundling these!
Provides:       bundled(hoedown) = 3.0.5
Provides:       bundled(jquery) = 2.1.4
Provides:       bundled(libbacktrace) = 6.1.0
Provides:       bundled(miniz) = 1.14

# The C compiler is needed at runtime just for linking.  Someday rustc might
# invoke the linker directly, and then we'll only need binutils.
# https://github.com/rust-lang/rust/issues/11937
Requires:       gcc

# ALL Rust libraries are private, because they don't keep an ABI.
%global _privatelibs lib.*-[[:xdigit:]]{8}[.]so.*
%global __provides_exclude ^(%{_privatelibs})$
%global __requires_exclude ^(%{_privatelibs})$

%description
Rust is a systems programming language that runs blazingly fast, prevents
segfaults, and guarantees thread safety.

This package includes the Rust compiler, standard library, and documentation
generator.


%package gdb
Summary:        GDB pretty printers for Rust
BuildArch:      noarch
Requires:       gdb

%description gdb
This package includes the rust-gdb script, which allows easier debugging of Rust
programs.


%package doc
Summary:        Documentation for Rust
# NOT BuildArch:      noarch
# Note, while docs are mostly noarch, some things do vary by target_arch.
# Koji will fail the build in rpmdiff if two architectures build a noarch
# subpackage differently, so instead we have to keep its arch.

%description doc
This package includes HTML documentation for the Rust programming language and
its standard library.


# TODO: consider a rust-std package containing .../rustlib/$target
# This might allow multilib cross-compilation to work naturally.


%prep
%setup -q -n %{rustc_package}

%if %with bootstrap
find %{sources} -name '%{bootstrap_root}.tar.gz' -exec tar -xvzf '{}' ';'
test -f '%{local_rust_root}/bin/rustc'
%endif

%patch1 -p1 -b .no-neon
%patch2 -p1 -b .less-neon

# unbundle
rm -rf src/jemalloc/
%if %without bundled_llvm
rm -rf src/llvm/
%endif

# extract bundled licenses for packaging
cp src/rt/hoedown/LICENSE src/rt/hoedown/LICENSE-hoedown
sed -e '/*\//q' src/libbacktrace/backtrace.h \
  >src/libbacktrace/LICENSE-libbacktrace

# rust-gdb has hardcoded SYSROOT/lib -- let's make it noarch
sed -i.noarch -e 's#DIRECTORY=".*"#DIRECTORY="%{_datadir}/%{name}/etc"#' \
  src/etc/rust-gdb

# These tests assume that alloc_jemalloc is present
sed -i.jemalloc -e '1i // ignore-test jemalloc is disabled' \
  src/test/compile-fail/allocator-dylib-is-system.rs \
  src/test/compile-fail/allocator-rust-dylib-is-jemalloc.rs \
  src/test/run-pass/allocator-default.rs

# Fedora's LLVM doesn't support any mips targets -- see "llc -version".
# Fixed properly by Rust PR36344, which should be released in 1.13.
sed -i.nomips -e '/target=mips/,+1s/^/# unsupported /' \
  src/test/run-make/atomic-lock-free/Makefile

%if %without bootstrap
# The hardcoded stage0 "lib" is inappropriate when using Fedora's own rustc
sed -i.libdir -e '/^HLIB_RELATIVE/s/lib$/$$(CFG_LIBDIR_RELATIVE)/' mk/main.mk
%endif

%if 0%{?rhel}
sed -i.cmake -e 's/CFG_CMAKE cmake/&3/' configure
%endif

%if %with llvm_static
# Static linking to distro LLVM needs to add -lffi
# https://github.com/rust-lang/rust/issues/34486
sed -i.ffi -e '$a #[link(name = "ffi")] extern {}' \
  src/librustc_llvm/lib.rs
%endif


%build

%ifarch aarch64
%if %with bootstrap
# Upstream binaries have a 4k-paged jemalloc, which breaks with Fedora 64k pages.
# https://github.com/rust-lang/rust/issues/36994
export MALLOC_CONF=lg_dirty_mult:-1
%endif
%endif

%configure --disable-option-checking \
  --build=%{rust_triple} --host=%{rust_triple} --target=%{rust_triple} \
  --enable-local-rust --local-rust-root=%{local_rust_root} \
  %{!?with_bundled_llvm:--llvm-root=%{_prefix} --disable-codegen-tests} \
  --disable-jemalloc \
  --disable-rpath \
  --enable-debuginfo \
  --release-channel=%{channel}

%make_build VERBOSE=1


%install
%make_install VERBOSE=1

# Remove installer artifacts (manifests, uninstall scripts, etc.)
find %{buildroot}/%{_libdir}/rustlib/ -maxdepth 1 -type f -exec rm -v '{}' '+'

# We don't want to ship the target shared libraries for lack of any Rust ABI.
find %{buildroot}/%{_libdir}/rustlib/ -type f -name '*.so' -exec rm -v '{}' '+'

# The remaining shared libraries should be executable for debuginfo extraction.
find %{buildroot}/%{_libdir}/ -type f -name '*.so' -exec chmod -v +x '{}' '+'

# They also don't need the .rustc metadata anymore, so they won't support linking.
# (but this needs the rhbz1380961 fix, or else eu-strip will clobber .dynsym)
%if 0%{?fedora} >= 25
find %{buildroot}/%{_libdir}/ -type f -name '*.so' -exec objcopy -R .rustc '{}' ';'
%endif

# FIXME: __os_install_post will strip the rlibs
# -- should we find a way to preserve debuginfo?

# Remove unwanted documentation files (we already package them)
rm -f %{buildroot}/%{_docdir}/%{name}/README.md
rm -f %{buildroot}/%{_docdir}/%{name}/COPYRIGHT
rm -f %{buildroot}/%{_docdir}/%{name}/LICENSE-APACHE
rm -f %{buildroot}/%{_docdir}/%{name}/LICENSE-MIT

# Sanitize the HTML documentation
find %{buildroot}/%{_docdir}/%{name}/html -empty -delete
find %{buildroot}/%{_docdir}/%{name}/html -type f -exec chmod -x '{}' '+'

# Move rust-gdb's python scripts so they're noarch
mkdir -p %{buildroot}/%{_datadir}/%{name}
mv -v %{buildroot}/%{_libdir}/rustlib/etc %{buildroot}/%{_datadir}/%{name}/


%check
# Note, many of the tests execute in parallel threads,
# so it's better not to use a parallel make here.
# The results are not stable on koji, so mask errors and just log it.
make check-lite VERBOSE=1 -k || python2 src/etc/check-summary.py tmp/*.log || :


%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig


%files
%license COPYRIGHT LICENSE-APACHE LICENSE-MIT
%license src/libbacktrace/LICENSE-libbacktrace
%license src/rt/hoedown/LICENSE-hoedown
%doc README.md
%{_bindir}/rustc
%{_bindir}/rustdoc
%{_mandir}/man1/rustc.1*
%{_mandir}/man1/rustdoc.1*
%{_libdir}/lib*
%dir %{_libdir}/rustlib
%{_libdir}/rustlib/%{rust_triple}


%files gdb
%{_bindir}/rust-gdb
%{_datadir}/%{name}


%files doc
%dir %{_docdir}/%{name}
%license %{_docdir}/%{name}/html/FiraSans-LICENSE.txt
%license %{_docdir}/%{name}/html/Heuristica-LICENSE.txt
%license %{_docdir}/%{name}/html/LICENSE-APACHE.txt
%license %{_docdir}/%{name}/html/LICENSE-MIT.txt
%license %{_docdir}/%{name}/html/SourceCodePro-LICENSE.txt
%license %{_docdir}/%{name}/html/SourceSerifPro-LICENSE.txt
%doc %{_docdir}/%{name}/html/


%changelog
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
