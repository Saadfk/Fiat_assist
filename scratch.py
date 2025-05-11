#!/usr/bin/env python3
import os

TARGET = "AI_FIAT"
for dirpath, _, filenames in os.walk("."):
    if "venv" in dirpath or ".git" in dirpath:
        continue
    for fname in filenames:
        if not fname.endswith(".py"):
            continue
        path = os.path.join(dirpath, fname)
        with open(path, encoding="utf-8", errors="ignore") as f:
            for num, line in enumerate(f, 1):
                if TARGET in line:
                    print(f"{path}:{num}: {line.strip()}")
