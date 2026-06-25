#!/usr/bin/env python3
"""scan-project — detect programming languages used in a project directory.
Scans file extensions and key config files to determine the project's language mix.
Usage: python scan-project.py [directory] | python scan-project.py --json"""

import sys, json
from pathlib import Path
from collections import Counter

EXTENSION_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".jsx": "JavaScript (React)",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".fs": "F#",
    ".vb": "Visual Basic",
    ".rb": "Ruby",
    ".php": "PHP",
    ".scala": "Scala",
    ".clj": "Clojure",
    ".cljs": "ClojureScript",
    ".edn": "Clojure (EDN)",
    ".ex": "Elixir",
    ".exs": "Elixir (Script)",
    ".erl": "Erlang",
    ".hrl": "Erlang Header",
    ".hs": "Haskell",
    ".lhs": "Haskell (Literate)",
    ".ml": "OCaml",
    ".mli": "OCaml Interface",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Zsh",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell Module",
    ".psd1": "PowerShell Data",
    ".r": "R",
    ".R": "R",
    ".rmd": "R Markdown",
    ".lua": "Lua",
    ".sql": "SQL",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".proto": "Protobuf",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".md": "Markdown",
    ".mdx": "MDX",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".html": "HTML",
    ".htm": "HTML",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".astro": "Astro",
    ".tf": "Terraform",
    ".dockerfile": "Docker",
    ".makefile": "Makefile",
    ".cmake": "CMake",
    ".nim": "Nim",
    ".zig": "Zig",
    ".dart": "Dart",
    ".purs": "PureScript",
    ".elm": "Elm",
}

CONFIG_MARKERS = {
    "package.json": "Node.js/JavaScript",
    "tsconfig.json": "TypeScript",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java/Kotlin (Gradle)",
    "build.gradle.kts": "Kotlin (Gradle)",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "Pipfile": "Python",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "mix.exs": "Elixir",
    "rebar.config": "Erlang",
    "stack.yaml": "Haskell",
    "cabal.project": "Haskell",
    "Makefile": "C/C++ (Make)",
    "CMakeLists.txt": "C/C++ (CMake)",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker",
    "docker-compose.yaml": "Docker",
    ".claude": "Claude Code",
}


def scan_directory(root: Path, max_files: int = 2000) -> dict:
    """Scan directory for programming language usage."""
    ext_counter = Counter()
    config_hits = []
    total_files = 0
    ignored_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "target", "build", "dist", ".next", ".nuxt", ".cache",
        "vendor", ".tox", ".eggs", ".idea", ".vscode",
    }
    # NOTE: .claude is NOT ignored — it contains actual code

    for entry in root.rglob("*"):
        if any(p.name in ignored_dirs for p in entry.parents):
            continue
        if entry.name in ignored_dirs:
            continue

        if entry.is_file():
            total_files += 1
            if total_files > max_files:
                break

            # Check config markers
            if entry.name in CONFIG_MARKERS:
                config_hits.append(CONFIG_MARKERS[entry.name])

            # Count extensions
            ext = entry.suffix.lower()
            if ext in EXTENSION_MAP:
                ext_counter[EXTENSION_MAP[ext]] += 1

    primary = [lang for lang, count in ext_counter.most_common(5) if count > 2]
    detected = list(set(primary + config_hits))

    return {
        "directory": str(root),
        "total_files_scanned": total_files,
        "languages_detected": detected,
        "file_counts": dict(ext_counter.most_common(20)),
        "config_markers": config_hits,
        "primary_language": primary[0] if primary else "unknown",
    }


def main():
    directory = "."
    use_json = "--json" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        if args[0] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        directory = args[0]

    root = Path(directory).resolve()
    if not root.exists():
        print(f"Error: directory not found: {root}", file=sys.stderr)
        sys.exit(1)

    result = scan_directory(root)

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Project: {result['directory']}")
        print(f"Files scanned: {result['total_files_scanned']}")
        print(f"Primary language: {result['primary_language']}")
        print(f"Detected: {', '.join(result['languages_detected']) if result['languages_detected'] else 'none'}")
        if result["config_markers"]:
            print(f"Configs: {', '.join(result['config_markers'])}")
        print(f"\nTop extensions:")
        for lang, count in result["file_counts"].items():
            print(f"  {lang}: {count}")


if __name__ == "__main__":
    main()
