"""Pipe-only Tesseract execution inside the resource-limited OCR worker."""
import subprocess
import time

from bounded_pipes import PipeLimit, exchange

EXECUTABLE = '/usr/bin/tesseract'
MAX_OUTPUT = 2 * 1024 * 1024


def run(png, deadline, *, seconds=15, psm='3', config=None):
    if deadline <= time.monotonic():
        raise subprocess.TimeoutExpired('tesseract', seconds)
    args = [EXECUTABLE, 'stdin', 'stdout', '-l', 'eng', '--psm', psm,
            '-c', 'debug_file=/dev/null'] + ([config] if config else [])
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, close_fds=True)
    try:
        try:
            output = exchange(process, png, deadline=min(deadline, time.monotonic() + seconds),
                              max_output=MAX_OUTPUT)
        except PipeLimit as exc:
            if exc.code == 'timeout':
                raise subprocess.TimeoutExpired('tesseract', seconds) from None
            raise
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, 'tesseract')
        return output
    finally:
        if process.poll() is None:
            process.kill()
        process.stdin.close()
        process.stdout.close()
        process.wait()
