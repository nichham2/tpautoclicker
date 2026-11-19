"""TP Auto Clicker: auto clicker + screen-watching automation.

Run:  python tpautoclicker.py
"""
import sys

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from tpac.selftest import run

        sys.exit(run())
    from tpac.app import main

    main()
