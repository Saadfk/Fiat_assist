import time

class HeadlineAggregator:
    def __init__(self, flush_interval=5):
        self.flush_interval = flush_interval
        self.buffer = []
        self.last_line_time = 0

    def add_line(self, line):
        now = time.time()
        self.buffer.append(line)
        self.last_line_time = now

    def should_flush(self):
        if not self.buffer:
            return False
        return (time.time() - self.last_line_time) > self.flush_interval

    def flush(self):
        combined = "\n".join(self.buffer)
        self.buffer.clear()
        return combined
