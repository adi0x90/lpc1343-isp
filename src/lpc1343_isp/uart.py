"""Byte queue in front of the LPC1343 UART registers."""

from lpc1343_isp.map import LSR_RX_READY, LSR_TX_EMPTY, UART_DR, UART_LSR


class UartPort:
    """Answer the two registers the boot ROM actually polls.

    A read of the line-status register has bit 5 set so transmits never spin,
    and bit 0 set only when a typed byte is waiting. A read of the data
    register returns that byte. A write of the data register is the ROM
    printing.
    """

    def __init__(self) -> None:
        self.rx = bytearray()
        self.tx = bytearray()

    def push_rx(self, data: bytes) -> None:
        self.rx.extend(data)

    def take_tx(self) -> bytes:
        data = bytes(self.tx)
        self.tx.clear()
        return data

    def read(self, address: int, size: int) -> int | None:
        if address == UART_LSR:
            value = LSR_TX_EMPTY
            if self.rx:
                value |= LSR_RX_READY
            return value
        if address == UART_DR:
            if not self.rx:
                return 0
            return self.rx.pop(0)
        if UART_DR <= address < UART_DR + 0x1000:
            return 0
        return None

    def write(self, address: int, size: int, value: int) -> bool:
        if address == UART_DR:
            self.tx.append(value & 0xFF)
            return True
        if UART_DR <= address < UART_DR + 0x1000:
            return True
        return False
