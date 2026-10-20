"""Fresh OCR process: set OS limits before importing image/PDF libraries."""
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


def main():
    try:
        config = json.loads(sys.argv[1])
        if sys.platform != 'linux':
            raise Rejected('unavailable')
        try:
            apply_limits(config)
        except (ImportError, OSError, ValueError):
            raise Rejected('unavailable') from None
        import signal
        def terminate(_signal, _frame):
            # Let a waiting Tesseract wrapper execute its kill/wait finally.
            raise SystemExit(1)
        signal.signal(signal.SIGTERM, terminate)
        # Only the shipped, absolute script directory, never cwd or user input.
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from bounded_pipes import PipeLimit
        import ocr_engine
        import ocr_tesseract
        ocr_tesseract.EXECUTABLE = config['tesseract']
        raw = sys.stdin.buffer.read(config['max_bytes'] + 1)
        if not raw or len(raw) > config['max_bytes']:
            raise Rejected('bytes' if config['mode'] == 'pdf' else 'image_bytes')
        try:
            result = ocr_engine.extract(raw, config)
        except PipeLimit as exc:
            raise Rejected(exc.code) from None
        except ValueError as exc:
            # Engine validation uses only reviewed codes, never library messages.
            raise Rejected(str(exc) if str(exc) in ocr_engine.ERROR_CODES else 'unreadable') from None
        result['ok'] = True
    except Rejected as exc:
        result = {'ok': False, 'error': str(exc)}
    except MemoryError:
        result = {'ok': False, 'error': 'resource'}
    except ImportError:
        result = {'ok': False, 'error': 'unavailable'}
    except Exception:
        result = {'ok': False, 'error': 'unreadable'}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True, separators=(',', ':')).encode())


if __name__ == '__main__':
    main()
