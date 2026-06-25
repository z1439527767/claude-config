#!/usr/bin/env python3
"""detect-lang — ELD-C wrapper: detect language of text from stdin or args."""
import sys
import eldc

def main():
    eldc.init()
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read()
    if not text.strip():
        print("und")
        sys.exit(1)
    result = eldc.detect(text.strip())
    print(result)

if __name__ == "__main__":
    main()
