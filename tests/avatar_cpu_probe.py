"""Opt-in all-thread Python CPU and V8 sample profiles; never forces collection."""
import importlib.metadata
import threading
import time


def fields(stat, keys):
    return {key: getattr(stat, key) for key in keys}


class CpuProfiles:
    def __init__(self, cdp):
        self.cdp = cdp
        self.started = False
        self.result = None

    def start(self):
        import yappi
        assert importlib.metadata.version('yappi') == '1.7.3'
        assert not yappi.is_running()
        self.start_ns = time.monotonic_ns()
        self.cdp.send('Profiler.enable')
        self.cdp.send('Profiler.setSamplingInterval', {'interval': 2000})
        self.cdp.send('Profiler.start')
        yappi.clear_stats()
        yappi.set_clock_type('cpu')
        yappi.start(builtins=True, profile_threads=True)
        self.started = True
        self.start_end_ns = time.monotonic_ns()

    def stop(self):
        import yappi
        if not self.started:
            return self.result
        begin = time.monotonic_ns()
        yappi.stop()
        python_end_ns = time.monotonic_ns()
        js = self.cdp.send('Profiler.stop')['profile']
        js_end_ns = time.monotonic_ns()
        self.cdp.send('Profiler.disable')
        function_keys = ['name','module','lineno','ncall','nactualcall','builtin','ttot','tsub','index','ctx_id','ctx_name']
        child_keys = ['index','name','module','lineno','ncall','nactualcall','ttot','tsub']
        functions = []
        for f in yappi.get_func_stats():
            functions.append({**fields(f, function_keys), 'children': [fields(c, child_keys) for c in f.children]})
        threads = [fields(t, ['name','id','tid','ttot','sched_count']) for t in yappi.get_thread_stats()]
        self.result = {'acceptance':False, 'yappi_version':importlib.metadata.version('yappi'),
                       'python_clock':yappi.get_clock_type(),'python_all_threads':True,
                       'js_sampling_interval_us':2000, 'start_ns':self.start_ns,'start_end_ns':self.start_end_ns,
                       'stop_begin_ns':begin,'python_end_ns':python_end_ns,'js_end_ns':js_end_ns,
                       'functions':functions,'threads':threads,'js':js,
                       'live_threads':[{'name':t.name,'ident':t.ident,'native_id':t.native_id} for t in threading.enumerate()]}
        self.started = False
        yappi.clear_stats()
        return self.result
