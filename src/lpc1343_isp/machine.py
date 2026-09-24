"""Run the LPC1343 ISP command loop on Unicorn.

The machine maps the four windows the loop touches, plants the CRP word and
the flash floor word, and starts at isp_command_loop. It does not boot from
reset. A line is queued into the UART and execution stops when the ROM is
back in uart_getc with nothing left to read.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from unicorn import (
    UC_ARCH_ARM,
    UC_HOOK_CODE,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_UNMAPPED,
    UC_HOOK_MEM_WRITE,
    UC_MODE_THUMB,
    Uc,
    UcError,
)
from unicorn.arm_const import (
    UC_ARM_REG_CPSR,
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R12,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)
from unicorn.unicorn_const import (
    UC_MEM_FETCH_UNMAPPED,
    UC_MEM_READ_UNMAPPED,
    UC_MEM_WRITE_UNMAPPED,
)

from lpc1343_isp.map import (
    ARG_BUF0,
    ARG_SLOTS,
    ARG_STRIDE,
    ARG_TABLE,
    CRP_FLASH,
    CRP_PATTERNS,
    CRP_WORD,
    DEFAULT_FLOOR_BASE,
    ECHO_FLAG,
    FLASH_BASE,
    FLASH_SIZE,
    FLASHCFG_PAGE,
    FLOOR_BASE_FLASH,
    FLOOR_CMP,
    INITIAL_SP,
    REGION1_END_FLASH,
    REGION2_END_FLASH,
    REGION2_START_FLASH,
    ISP_LOOP,
    ROM_BASE,
    ROM_SIZE,
    SRAM_BASE,
    SRAM_SIZE,
    UART_PAGE,
    UART_POLL,
    VECTOR_RESET,
    VECTOR_SP,
)
from lpc1343_isp.uart import UartPort

_PAGE = 0x1000
# CPSR.T. emu_start also ORs 1 into the start address; both keep the core in Thumb.
_THUMB = 1 << 5


class RomImageError(ValueError):
    """The file is too small or is not this LPC1343 boot ROM."""


@dataclass(frozen=True)
class FloorHit:
    """Registers at the destination compare inside WriteMemoryHandler.

    dest is r3 and floor is r2 at that instruction, before the compare runs.
    The ROM refuses the write when dest < floor.
    """

    dest: int
    floor: int

    @property
    def refused(self) -> bool:
        return self.dest < self.floor


@dataclass(frozen=True)
class RunResult:
    """One queued line, run until the ROM blocks on the next byte."""

    tx: bytes
    stop: str
    steps: int
    pc: int
    floor: FloorHit | None
    detail: str = ""

    @property
    def text(self) -> str:
        return self.tx.decode("latin-1")


def load_rom_image(rom: bytes) -> bytes:
    """Return the first 16 KiB, which is the boot ROM mapped at 0x1FFF0000."""

    if len(rom) < ROM_SIZE:
        raise RomImageError(f"ROM image is {len(rom)} bytes; need at least {ROM_SIZE:#x}")
    image = bytes(rom[:ROM_SIZE])
    sp = int.from_bytes(image[0:4], "little")
    reset = int.from_bytes(image[4:8], "little")
    if sp != VECTOR_SP or reset != VECTOR_RESET:
        raise RomImageError(
            f"ROM header SP={sp:#x} reset={reset:#x} is not the LPC1343 boot ROM "
            f"(SP={VECTOR_SP:#x} reset={VECTOR_RESET:#x})"
        )
    return image


class LpcMachine:
    """One ISP session. reset() rebuilds flash, SRAM, and the register file."""

    def __init__(
        self,
        rom: bytes,
        *,
        crp: str = "1",
        floor_base: int = DEFAULT_FLOOR_BASE,
        budget: int = 2_000_000,
    ) -> None:
        if crp not in CRP_PATTERNS:
            known = ", ".join(CRP_PATTERNS)
            raise ValueError(f"unknown crp {crp!r}; expected one of {known}")
        if budget < 1:
            raise ValueError("budget must be a positive instruction count")
        self.image = load_rom_image(rom)
        self.crp = crp
        self.pattern = CRP_PATTERNS[crp]
        self.floor_base = floor_base & 0xFFFFFFFF
        self.budget = budget
        self.uart = UartPort()
        self.mmio_pages: list[int] = []
        self.last_pcs: deque[int] = deque(maxlen=24)
        self._injecting = False
        self._resume_pc: int | None = None
        self._halt: str | None = None
        self._floor: FloorHit | None = None
        self._error = ""
        self.steps = 0
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self._map_windows()
        self._install_hooks()
        self.reset()

    def reset(self) -> None:
        """Restore the planted session. Queued UART bytes are discarded."""

        uc = self.uc
        uc.mem_write(FLASH_BASE, b"\x00" * FLASH_SIZE)
        uc.mem_write(SRAM_BASE, b"\x00" * SRAM_SIZE)
        uc.mem_write(ROM_BASE, self.image)
        uc.mem_write(UART_PAGE, b"\x00" * _PAGE)
        uc.mem_write(FLASHCFG_PAGE, b"\x00" * _PAGE)
        self._plant()
        self.uart.rx.clear()
        self.uart.tx.clear()
        for reg in range(UC_ARM_REG_R0, UC_ARM_REG_R12 + 1):
            uc.reg_write(reg, 0)
        uc.reg_write(UC_ARM_REG_LR, 0)
        uc.reg_write(UC_ARM_REG_SP, INITIAL_SP)
        uc.reg_write(UC_ARM_REG_CPSR, _THUMB)
        self._resume_pc = None
        self.last_pcs.clear()

    def read_mem(self, address: int, size: int) -> bytes:
        return bytes(self.uc.mem_read(address, size))

    def push_line(self, line: str) -> None:
        """Queue one ISP line. A trailing CR or LF on `line` is replaced with CR."""

        try:
            raw = line.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("ISP lines are ASCII") from exc
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        self.uart.push_rx(raw + b"\r")

    def run(self) -> RunResult:
        """Execute until the ROM polls the UART with an empty receive queue."""

        self._halt = None
        self._floor = None
        self._error = ""
        self.steps = 0
        pc = ISP_LOOP if self._resume_pc is None else self._resume_pc
        try:
            self.uc.emu_start(pc | 1, 0xFFFFFFFF, timeout=0, count=self.budget)
        except UcError as exc:
            if self._halt is None:
                self._halt = "error"
                self._error = str(exc)
        stopped = self.uc.reg_read(UC_ARM_REG_PC) & ~1
        self._resume_pc = stopped
        if self._halt is None:
            self._halt = "budget"
            self._error = "instruction budget exhausted"
        return RunResult(
            tx=self.uart.take_tx(),
            stop=self._halt,
            steps=self.steps,
            pc=stopped,
            floor=self._floor,
            detail=self._error,
        )

    def command(self, line: str) -> RunResult:
        self.push_line(line)
        return self.run()

    def _plant(self) -> None:
        sram_last = (SRAM_BASE + SRAM_SIZE - 1) & 0xFFFFFFFF
        self._w32(CRP_FLASH, self.pattern)
        self._w32(CRP_WORD, self.pattern)
        self._w32(FLOOR_BASE_FLASH, self.floor_base)
        self._w32(REGION1_END_FLASH, sram_last)
        self._w32(REGION2_START_FLASH, SRAM_BASE)
        self._w32(REGION2_END_FLASH, sram_last)
        self._w32(ECHO_FLAG, 0)
        for slot in range(ARG_SLOTS):
            self._w32(ARG_TABLE + 4 * slot, ARG_BUF0 + slot * ARG_STRIDE)

    def _w32(self, address: int, value: int) -> None:
        self.uc.mem_write(address, (value & 0xFFFFFFFF).to_bytes(4, "little"))

    def _map_windows(self) -> None:
        uc = self.uc
        uc.mem_map(FLASH_BASE, FLASH_SIZE)
        uc.mem_map(SRAM_BASE, SRAM_SIZE)
        uc.mem_map(ROM_BASE, ROM_SIZE)
        uc.mem_map(UART_PAGE, _PAGE)
        uc.mem_map(FLASHCFG_PAGE, _PAGE)

    def _install_hooks(self) -> None:
        uc = self.uc
        # mem_write inside the read hook would otherwise look like a ROM store
        # and, for the data register, append a byte the chip never transmitted.
        uart = self.uart

        def on_read(uc: Uc, access: int, address: int, size: int, value: int, user: object) -> None:
            if self._injecting:
                return
            word = uart.read(address, size)
            if word is None:
                return
            self._injecting = True
            try:
                uc.mem_write(address, (word & 0xFFFFFFFF).to_bytes(4, "little")[:size])
            finally:
                self._injecting = False

        def on_write(uc: Uc, access: int, address: int, size: int, value: int, user: object) -> None:
            if self._injecting:
                return
            uart.write(address, size, value)

        def on_unmapped(uc: Uc, access: int, address: int, size: int, value: int, user: object) -> bool:
            if access == UC_MEM_FETCH_UNMAPPED:
                self._halt = "fetch"
                self._error = f"instruction fetch from {address:#x}"
                return False
            if access not in (UC_MEM_READ_UNMAPPED, UC_MEM_WRITE_UNMAPPED):
                self._halt = "error"
                self._error = f"unmapped access {access} at {address:#x}"
                return False
            page = address & ~(_PAGE - 1)
            if page not in self.mmio_pages and len(self.mmio_pages) < 32:
                self.mmio_pages.append(page)
            try:
                uc.mem_map(page, _PAGE)
            except UcError:
                pass
            return True

        def on_code(uc: Uc, address: int, size: int, user: object) -> None:
            self.steps += 1
            self.last_pcs.append(address)
            if address == FLOOR_CMP and self._floor is None:
                dest = uc.reg_read(UC_ARM_REG_R3) & 0xFFFFFFFF
                floor = uc.reg_read(UC_ARM_REG_R2) & 0xFFFFFFFF
                self._floor = FloorHit(dest, floor)
            # uart_getc spins here until LSR bit 0 is set. An empty queue means
            # the ROM has finished this line and is blocked on the next byte.
            if address == UART_POLL and not uart.rx:
                self._halt = "reply" if b"\n" in uart.tx else "wait"
                uc.emu_stop()

        last = UART_PAGE + _PAGE - 1
        uc.hook_add(UC_HOOK_MEM_READ, on_read, begin=UART_PAGE, end=last)
        uc.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=UART_PAGE, end=last)
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
        uc.hook_add(UC_HOOK_CODE, on_code)
