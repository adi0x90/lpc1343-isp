"""ISP replies from the real boot ROM. Skipped when the dump is absent."""

from __future__ import annotations

import unittest

from lpc1343_isp.machine import LpcMachine, RomImageError, load_rom_image
from lpc1343_isp.map import ROM_SIZE, UART_POLL

from support import load_rom


def uu_char(value: int) -> str:
    value &= 0x3F
    if value == 0:
        return "`"
    return chr(value + 0x20)


def uu_line(payload: bytes) -> str:
    """One ISP data line: length character, then 4 characters per 3 bytes."""

    padded = payload + b"\x00" * ((3 - len(payload) % 3) % 3)
    chars: list[str] = []
    for index in range(0, len(padded), 3):
        b0, b1, b2 = padded[index : index + 3]
        chars.append(uu_char(b0 >> 2))
        chars.append(uu_char(((b0 & 3) << 4) | (b1 >> 4)))
        chars.append(uu_char(((b1 & 0xF) << 2) | (b2 >> 6)))
        chars.append(uu_char(b2 & 0x3F))
    length = "`" if len(payload) == 0 else chr(len(payload) + 0x20)
    return length + "".join(chars)


class ImageCheckTest(unittest.TestCase):
    def test_short_image_is_rejected(self) -> None:
        with self.assertRaises(RomImageError):
            load_rom_image(b"\x00" * 16)

    def test_wrong_header_is_rejected(self) -> None:
        blob = b"\x00" * ROM_SIZE
        with self.assertRaises(RomImageError):
            load_rom_image(blob)

    def test_unknown_crp_is_rejected(self) -> None:
        image = bytearray(b"\x00" * ROM_SIZE)
        image[0:4] = (0x10000FFC).to_bytes(4, "little")
        image[4:8] = (0x1FFF0105).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            LpcMachine(bytes(image), crp="9")


@unittest.skipUnless(load_rom() is not None, "LPC1343 boot ROM dump is not available")
class WriteFloorTest(unittest.TestCase):
    def setUp(self) -> None:
        rom = load_rom()
        assert rom is not None
        self.rom = rom

    def _diag(self, machine: LpcMachine, result) -> str:
        trail = " ".join(f"{pc:#x}" for pc in machine.last_pcs)
        pages = " ".join(f"{page:#x}" for page in machine.mmio_pages)
        return f"stop={result.stop} tx={result.tx!r} pc={result.pc:#x} steps={result.steps} detail={result.detail!r} mmio=[{pages}] trail=[{trail}]"

    def test_crp1_refuses_below_the_floor(self) -> None:
        machine = LpcMachine(self.rom, crp="1")
        result = machine.command("W 268435456 4")
        self.assertEqual(result.stop, "reply", self._diag(machine, result))
        self.assertEqual(result.text.strip(), "19", self._diag(machine, result))
        self.assertEqual(result.pc, UART_POLL)
        self.assertIsNotNone(result.floor)
        assert result.floor is not None
        self.assertEqual(result.floor.dest, 0x10000000)
        self.assertEqual(result.floor.floor, 0x10000300)
        self.assertTrue(result.floor.refused)

    def test_crp1_accepts_the_floor_address(self) -> None:
        machine = LpcMachine(self.rom, crp="1")
        result = machine.command("W 268436224 4")
        self.assertEqual(result.stop, "reply", self._diag(machine, result))
        self.assertEqual(result.text.strip(), "0")
        assert result.floor is not None
        self.assertEqual(result.floor.dest, 0x10000300)
        self.assertEqual(result.floor.floor, 0x10000300)
        self.assertFalse(result.floor.refused)

    def test_one_below_the_floor_is_refused(self) -> None:
        machine = LpcMachine(self.rom, crp="1")
        result = machine.command("W 268436223 4")
        self.assertEqual(result.text.strip(), "19", self._diag(machine, result))
        assert result.floor is not None
        self.assertEqual(result.floor.dest, 0x100002FF)
        self.assertTrue(result.floor.refused)

    def test_crp2_and_crp3_refuse_at_the_gate(self) -> None:
        for level in ("2", "3"):
            machine = LpcMachine(self.rom, crp=level)
            result = machine.command("W 268436224 4")
            self.assertEqual(result.stop, "reply", self._diag(machine, result))
            self.assertEqual(result.text.strip(), "19", self._diag(machine, result))
            self.assertIsNone(result.floor, self._diag(machine, result))

    def test_crp_none_accepts_a_low_address(self) -> None:
        machine = LpcMachine(self.rom, crp="none")
        result = machine.command("W 268435456 4")
        self.assertEqual(result.stop, "reply", self._diag(machine, result))
        self.assertEqual(result.text.strip(), "0", self._diag(machine, result))
        self.assertIsNone(result.floor)

    def test_floor_base_is_the_flash_word_plus_0x200(self) -> None:
        machine = LpcMachine(self.rom, crp="1", floor_base=0x10000000)
        low = machine.command("W 268435456 4")
        self.assertEqual(low.text.strip(), "19", self._diag(machine, low))
        assert low.floor is not None
        self.assertEqual(low.floor.floor, 0x10000200)
        machine.reset()
        high = machine.command("W 268435968 4")
        self.assertEqual(high.text.strip(), "0", self._diag(machine, high))
        assert high.floor is not None
        self.assertEqual(high.floor.dest, 0x10000200)
        self.assertFalse(high.floor.refused)

    def test_a_refused_write_leaves_the_prompt_ready(self) -> None:
        machine = LpcMachine(self.rom, crp="1")
        first = machine.command("W 268435456 4")
        second = machine.command("W 268436224 4")
        self.assertEqual(first.text.strip(), "19")
        self.assertEqual(second.text.strip(), "0", self._diag(machine, second))

    def test_accepted_write_stores_the_data_line(self) -> None:
        dest = 0x10000800
        payload = bytes((0x11, 0x22, 0x33, 0x44))
        machine = LpcMachine(self.rom, crp="1")
        opened = machine.command(f"W {dest} 4")
        self.assertEqual(opened.text.strip(), "0", self._diag(machine, opened))
        stored = machine.command(uu_line(payload))
        self.assertEqual(stored.stop, "wait", self._diag(machine, stored))
        self.assertEqual(machine.read_mem(dest, 4), payload, self._diag(machine, stored))
        checksum = machine.command(str(sum(payload)))
        self.assertEqual(checksum.stop, "reply", self._diag(machine, checksum))
        self.assertEqual(checksum.text.strip(), "OK")
        self.assertEqual(machine.read_mem(dest, 4), payload)


if __name__ == "__main__":
    unittest.main()
