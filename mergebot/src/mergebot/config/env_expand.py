import os
import re

def expand_env(text: str) -> str:
    pattern = re.compile(r'\$\{([A-Z0-9_]+)\}')
    return pattern.sub(lambda m: os.getenv(m.group(1), ""), text)
