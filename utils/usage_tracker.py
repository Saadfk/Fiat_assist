import os
import json
import time
from collections import deque

class UsageTracker:
    def __init__(self, usage_file="tweet_usage.json", max_attempts=100, time_window=24 * 3600):
        self.usage_file = usage_file
        self.max_attempts = max_attempts
        self.time_window = time_window
        self.attempts = deque()
        self.load_usage()
        self.prune()

    def load_usage(self):
        if os.path.exists(self.usage_file):
            with open(self.usage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.attempts = deque(data)
        else:
            self.attempts = deque()

    def save_usage(self):
        with open(self.usage_file, "w", encoding="utf-8") as f:
            json.dump(list(self.attempts), f)

    def prune(self):
        now = time.time()
        while self.attempts and (now - self.attempts[0]) > self.time_window:
            self.attempts.popleft()

    def can_post(self):
        self.prune()
        return len(self.attempts) < self.max_attempts

    def record_post(self):
        now = time.time()
        self.attempts.append(now)
        self.save_usage()
