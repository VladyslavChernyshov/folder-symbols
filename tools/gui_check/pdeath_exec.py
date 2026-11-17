#!/usr/bin/env python3
"""pdeath_exec.py PARENT_PID PROGRAM [ARGS...]: run PROGRAM so that the kernel kills it (SIGKILL) when the
process that started it dies, even by SIGKILL (prctl PR_SET_PDEATHSIG, kept across exec). Used by the GUI
harness for Xvfb, dbus-daemon, the scenario processes and the second launches. Standard library only."""
import ctypes
import os
import signal
import sys

PR_SET_PDEATHSIG = 1


def main(argv):
    if len(argv) < 3:
        sys.exit("usage: pdeath_exec.py PARENT_PID PROGRAM [ARGS...]")
    parent = int(argv[1])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
        sys.exit(f"pdeath_exec: prctl failed: {os.strerror(ctypes.get_errno())}")
    if os.getppid() != parent:            # the parent died before prctl: it would never signal us
        sys.exit("pdeath_exec: the parent process is gone")
    os.execvp(argv[2], argv[2:])


if __name__ == "__main__":
    main(sys.argv)
