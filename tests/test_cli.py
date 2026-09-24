"""CLI wiring. ROM cases are skipped when the dump is absent."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lpc1343_isp.cli import main

from support import rom_path


class CliTest(unittest.TestCase):
    def test_missing_arguments_exit(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            main([])
        self.assertEqual(caught.exception.code, 2)

    def test_missing_file_is_reported(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(["-rom", "/no/such/LPC1343_bootloader_dump.bin", "--command", "W 1 4"])
        self.assertEqual(rc, 2)
        self.assertIn("not found", err.getvalue())

    @unittest.skipUnless(rom_path() is not None, "LPC1343 boot ROM dump is not available")
    def test_batch_floor_break_and_crp2(self) -> None:
        rom = rom_path()
        assert rom is not None
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(
                [
                    "-rom",
                    str(rom),
                    "--crp",
                    "1",
                    "--break",
                    "floor",
                    "--command",
                    "W 268435456 4",
                ]
            )
        self.assertEqual(rc, 0, err.getvalue())
        text = out.getvalue()
        self.assertIn("floor: dest=0x10000000 floor=0x10000300 -> 19", text)
        self.assertIn("19", text.splitlines()[-1])

        out2 = io.StringIO()
        err2 = io.StringIO()
        with redirect_stdout(out2), redirect_stderr(err2):
            rc2 = main(["-rom", str(rom), "--crp", "2", "--command", "W 268436224 4"])
        self.assertEqual(rc2, 0, err2.getvalue())
        self.assertEqual(out2.getvalue().strip(), "19")

    @unittest.skipUnless(rom_path() is not None, "LPC1343 boot ROM dump is not available")
    def test_break_meta_applies_to_the_next_command(self) -> None:
        rom = rom_path()
        assert rom is not None
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(
                [
                    "-rom",
                    str(rom),
                    "--crp",
                    "1",
                    "--command",
                    ".break",
                    "--command",
                    "W 268435456 4",
                ]
            )
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("floor: dest=0x10000000 floor=0x10000300 -> 19", out.getvalue())


if __name__ == "__main__":
    unittest.main()
