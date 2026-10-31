"""givememd <url> [--no-links] [--trace]   -- print LLM-ready markdown for a web page (fetched from this machine)."""
import sys

from . import UnsafeURL, read


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args or '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__.strip()); sys.exit(0 if args or '--help' in sys.argv or '-h' in sys.argv else 2)
    try:
        md, r = read(args[0], links='--no-links' not in sys.argv)
    except UnsafeURL as e:
        sys.exit(f'refused: {e}')
    if '--trace' in sys.argv:
        print('\n'.join(r.trace), file=sys.stderr)
    if md is None:
        sys.exit(f'could not read {r.url}')
    print(md)


if __name__ == '__main__':
    main()
