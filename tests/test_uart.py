"""UART queue behavior, with no ROM and no Unicorn."""

from __future__ import annotations

import unittest

from lpc1343_isp.map import LSR_RX_READY, LSR_TX_EMPTY, UART_DR, UART_LSR
from lpc1343_isp.uart import UartPort


class UartPortTest(unittest.TestCase):
    def test_lsr_tracks_the_receive_queue(self) -> None:
        port = UartPort()
        self.assertEqual(port.read(UART_LSR, 4), LSR_TX_EMPTY)
        port.push_rx(b"W\r")
        self.assertEqual(port.read(UART_LSR, 4), LSR_TX_EMPTY | LSR_RX_READY)
        self.assertEqual(port.read(UART_DR, 4), ord("W"))
        self.assertEqual(port.read(UART_DR, 4), 0x0D)
        self.assertEqual(port.read(UART_DR, 4), 0)
        self.assertEqual(port.read(UART_LSR, 4), LSR_TX_EMPTY)

    def test_transmit_keeps_the_low_byte(self) -> None:
        port = UartPort()
        self.assertTrue(port.write(UART_DR, 4, 0x131))
        self.assertEqual(port.take_tx(), b"1")
        self.assertEqual(port.take_tx(), b"")

    def test_other_uart_offsets_are_inert(self) -> None:
        port = UartPort()
        self.assertEqual(port.read(UART_DR + 0x20, 4), 0)
        self.assertTrue(port.write(UART_DR + 0x20, 4, 0xFF))
        self.assertEqual(port.take_tx(), b"")
        self.assertIsNone(port.read(UART_DR + 0x1000, 4))
        self.assertFalse(port.write(UART_DR + 0x1000, 4, 1))


if __name__ == "__main__":
    unittest.main()
