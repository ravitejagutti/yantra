@echo off
REM Yantra Global Launcher - thin OS-native stub.
REM All actual logic (default to "launch yantra", setup, flags) lives in
REM yantra.py, which runs identically on every OS. This file exists only
REM because Windows requires a .bat/.cmd/.exe to resolve a bare command
REM name like "yantra" from PATH - see yantra (no extension) for the
REM equivalent macOS/Linux stub.
REM
REM Usage:
REM   yantra          Launch enhanced Claude session (with Headroom if installed)
REM   yantra -v       Verbose mode
REM   yantra setup    One-time: install Headroom
python "%~dp0yantra.py" %*
