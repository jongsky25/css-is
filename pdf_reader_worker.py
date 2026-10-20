"""Private native-PDF worker. Only bounded bytes/JSON cross its standard pipes.

Started with an isolated interpreter; never imports the application, database,
OCR renderer or provider clients. Linux resource limits precede parser imports.
"""
import io
import json
import sys


class Rejected(Exception):
    pass


def apply_limits(config):
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CPU, (config['cpu'], config['cpu'] + 1))
    resource.setrlimit(resource.RLIMIT_AS, (config['memory'], config['memory']))


def extract(raw, config):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted:
        raise Rejected('encrypted')
    count = len(reader.pages)
    if count > config['max_pages']:
        raise Rejected('pages')
    selection = config['selection']
    indices = range(count) if selection == 'all' else ([0] if selection == 'first' else [1])
    if not count or any(index >= count for index in indices):
        raise Rejected('unreadable')
    pages, total = {}, 0
    for index in indices:
        text = reader.pages[index].extract_text() or ''
        total += len(text)
        if total > config['max_text']:
            raise Rejected('text')
        pages[str(index)] = text
    return {'ok': True, 'page_count': count, 'pages': pages}


def main():
    try:
        config = json.loads(sys.argv[1])
        if sys.platform != 'linux':
            raise Rejected('unavailable')
        try:
            apply_limits(config)
        except (ImportError, OSError, ValueError):
            raise Rejected('unavailable') from None
        raw = sys.stdin.buffer.read(config['max_bytes'] + 1)
        if not raw or len(raw) > config['max_bytes']:
            raise Rejected('bytes')
        if not raw.startswith(b'%PDF-'):
            raise Rejected('unreadable')
        result = extract(raw, config)
    except Rejected as exc:
        result = {'ok': False, 'error': str(exc)}
    except MemoryError:
        result = {'ok': False, 'error': 'resource'}
    except Exception:
        # Parser exception text can contain document content; never return it.
        result = {'ok': False, 'error': 'unreadable'}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True, separators=(',', ':')).encode())


if __name__ == '__main__':
    main()
