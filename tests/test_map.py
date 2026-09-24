"""Relationships between the planted addresses. No emulator."""

from __future__ import annotations

import unittest

from lpc1343_isp.map import (
    ARG_BUF0,
    ARG_SLOTS,
    ARG_STRIDE,
    ARG_TABLE,
    CRP_PATTERNS,
    DEFAULT_FLOOR_BASE,
    FLOOR_CMP,
    INITIAL_SP,
    ISP_LOOP,
    ROM_BASE,
    ROM_SIZE,
    SRAM_BASE,
    SRAM_SIZE,
    SRAM_TOP,
    UART_POLL,
    VECTOR_RESET,
    VECTOR_SP,
)


class MapTest(unittest.TestCase):
    def test_windows_and_floor(self) -> None:
        self.assertEqual(SRAM_TOP, SRAM_BASE + SRAM_SIZE)
        self.assertEqual(DEFAULT_FLOOR_BASE + 0x200, 0x10000300)
        self.assertLess(SRAM_BASE, DEFAULT_FLOOR_BASE)
        self.assertLess(DEFAULT_FLOOR_BASE + 0x200, INITIAL_SP)
        self.assertLess(INITIAL_SP, SRAM_TOP)
        self.assertEqual(INITIAL_SP & 7, 0)

    def test_pointer_table_sits_just_past_the_line_buffer(self) -> None:
        line_buf = ARG_TABLE - 0x94
        self.assertEqual(line_buf, 0x100001B4)
        self.assertEqual(line_buf + 0x46, ARG_BUF0)
        last = ARG_BUF0 + (ARG_SLOTS - 1) * ARG_STRIDE + ARG_STRIDE
        self.assertLessEqual(last, ARG_TABLE)

    def test_code_sites_are_inside_the_rom_window(self) -> None:
        for address in (ISP_LOOP, FLOOR_CMP, UART_POLL, VECTOR_RESET & ~1):
            self.assertGreaterEqual(address, ROM_BASE)
            self.assertLess(address, ROM_BASE + ROM_SIZE)
        self.assertEqual(VECTOR_SP, 0x10000FFC)

    def test_crp_patterns(self) -> None:
        self.assertEqual(CRP_PATTERNS["1"], 0x12345678)
        self.assertEqual(CRP_PATTERNS["2"], 0x87654321)
        self.assertEqual(CRP_PATTERNS["3"], 0x43218765)
        self.assertEqual(CRP_PATTERNS["none"], 0xFFFFFFFF)


if __name__ == "__main__":
    unittest.main()
