"""Bounded pipe transfer for trusted subprocess commands with untrusted input."""
import os
import selectors
import time


class PipeLimit(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def exchange(process, raw, *, deadline, max_output, cancelled=None):
    output, offset = bytearray(), 0
    with selectors.DefaultSelector() as selector:
        for pipe, event in ((process.stdin, selectors.EVENT_WRITE),
                            (process.stdout, selectors.EVENT_READ)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, event)
        reading = True
        while reading or process.poll() is None:
            if cancelled is not None and cancelled.is_set():
                raise PipeLimit('cancelled')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PipeLimit('timeout')
            for key, _ in selector.select(min(.05, remaining)):
                pipe = key.fileobj
                if pipe is process.stdin:
                    try:
                        offset += os.write(pipe.fileno(), memoryview(raw)[offset:offset + 65536])
                    except BrokenPipeError:
                        offset = len(raw)
                    if offset == len(raw):
                        selector.unregister(pipe)
                        pipe.close()
                else:
                    chunk = os.read(pipe.fileno(), 65536)
                    if not chunk:
                        selector.unregister(pipe)
                        reading = False
                    else:
                        if len(output) + len(chunk) > max_output:
                            raise PipeLimit('resource')
                        output.extend(chunk)
    return bytes(output)
