"""Entry point: python main.py   (``--backup`` = headless automatic backup, used by Windows Task Scheduler)"""
import sys

if __name__ == "__main__":
    if "--backup" in sys.argv[1:]:
        from vx7khata.autobackup import cli_main
        sys.exit(cli_main())
    from vx7khata.app import run
    sys.exit(run())
