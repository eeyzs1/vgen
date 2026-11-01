"""Optional GPU telemetry, sampled only during explicitly requested live jobs."""
import subprocess
import threading
import time


class GpuMetrics:
    def __init__(self):
        self.stop_event=threading.Event();self.peak_mib=None;self.samples=0;self.error=None
        self.started=time.monotonic();self.thread=None
    def sample(self):
        try:
            result=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,encoding='utf-8',timeout=3,check=True)
            values=[int(line.strip()) for line in result.stdout.splitlines() if line.strip()]
            if values:self.peak_mib=max(self.peak_mib or 0,sum(values));self.samples+=1
        except (OSError,subprocess.SubprocessError,ValueError) as exc:self.error=str(exc)
    def start(self):
        def loop():
            while not self.stop_event.is_set():
                self.sample()
                self.stop_event.wait(1)
        self.thread=threading.Thread(target=loop,daemon=True);self.thread.start()
        return self
    def finish(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=4)
        return dict(elapsed_seconds=time.monotonic()-self.started,gpu_peak_mib=self.peak_mib,
                    gpu_samples=self.samples,gpu_scope='total memory used across visible GPUs, including other applications',telemetry_error=self.error)
