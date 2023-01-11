#!/bin/bash
# vim: dict+=/usr/share/beakerlib/dictionary.vim cpt=.,w,b,u,t,i,k
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
#   runtest.sh of /tools/rust/Sanity/rpmbuild-librsvg2
#   Description: rpmbuild librsvg2
#   Author: Edjunior Machado <emachado@redhat.com>
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
#   Copyright (c) 2018 Red Hat, Inc.
#
#   This program is free software: you can redistribute it and/or
#   modify it under the terms of the GNU General Public License as
#   published by the Free Software Foundation, either version 2 of
#   the License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be
#   useful, but WITHOUT ANY WARRANTY; without even the implied
#   warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
#   PURPOSE.  See the GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program. If not, see http://www.gnu.org/licenses/.
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# Include Beaker environment
. /usr/share/beakerlib/beakerlib.sh || exit 1

PACKAGE="$(rpm -qf $(which rustc))"

rlJournalStart
    rlPhaseStartSetup
        rlAssertRpm $PACKAGE || rlDie "rustc not found. Aborting testcase..."
        rlRun "TmpDir=\$(mktemp -d)" 0 "Creating tmp directory"
        rlRun "pushd $TmpDir"
    rlPhaseEnd

    PKG_TO_BUILD=librsvg2
    rlPhaseStart FAIL ${PKG_TO_BUILD}FetchSrcAndInstallBuildDeps
        if ! rlCheckRpm $PKG_TO_BUILD; then
            rlRun "yum install -y $PKG_TO_BUILD ${YUM_SWITCHES}"
            rlAssertRpm $PKG_TO_BUILD
        fi
        rlFetchSrcForInstalled $PKG_TO_BUILD
        rlRun SRPM=$(ls -1 ${PKG_TO_BUILD}*src.rpm)
        rlRun "rpm -ivh $SRPM"
        rlRun SPECDIR="$(rpm -E '%{_specdir}')"

        # librsvg2 contains dynamic dependencies. builddep needs to be run
        # from the srpm (not the spec file) to be able to generate them:
        # https://fedoraproject.org/wiki/Changes/DynamicBuildRequires#rpmbuild
        rlRun "yum-builddep -y ${SRPM} ${YUM_SWITCHES}"
    rlPhaseEnd

    rlPhaseStartTest
        set -o pipefail
        rlRun "rpmbuild -bb ${SPECDIR}/${PKG_TO_BUILD}.spec |& tee ${SRPM}_rpmbuild.log"
        rlFileSubmit "${SRPM}_rpmbuild.log"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "popd"
        rlRun "rm -r $TmpDir" 0 "Removing tmp directory"
    rlPhaseEnd
rlJournalPrintText
rlJournalEnd
