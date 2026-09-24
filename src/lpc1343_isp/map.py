"""Fixed addresses for the LPC1343 ISP command loop."""

ROM_BASE = 0x1FFF0000
ROM_SIZE = 0x4000

FLASH_BASE = 0x00000000
FLASH_SIZE = 0x8000
CRP_FLASH = 0x000002FC
FLOOR_BASE_FLASH = 0x00000438
# parse_field (mode 0x67) treats a destination as mapped only when the
# address and the byte count sit inside one of three flash-resident windows.
# Window 1 starts at the floor base above. Its end, and a second window that
# covers all of SRAM, have to be planted too; otherwise every address comes
# back as 14 (ADDR_NOT_MAPPED) and the floor compare never gets to say 0.
REGION1_END_FLASH = 0x0000043C
REGION2_START_FLASH = 0x00000460
REGION2_END_FLASH = 0x00000464

SRAM_BASE = 0x10000000
SRAM_SIZE = 0x2000
SRAM_TOP = SRAM_BASE + SRAM_SIZE

ARG_TABLE = 0x10000248
ARG_BUF0 = 0x100001FA
ARG_STRIDE = 0x0F
ARG_SLOTS = 5
CRP_WORD = 0x10000184
ECHO_FLAG = 0x10000188

UART_PAGE = 0x40008000
UART_DR = 0x40008000
UART_LSR = 0x40008014
LSR_RX_READY = 1 << 0
LSR_TX_EMPTY = 1 << 5

FLASHCFG_PAGE = 0x4003C000

ISP_LOOP = 0x1FFF0FBC
FLOOR_CMP = 0x1FFF0DA0
# uart_getc loads the line-status register here and branches back while bit 0 is clear.
UART_POLL = 0x1FFF1BF8

# First two words of this boot ROM. Used to reject a file that is not the image.
VECTOR_SP = 0x10000FFC
VECTOR_RESET = 0x1FFF0105

# Initial stack for the lab session. The vector table says 0x10000ffc, which is
# below the CRP1 floor. Startup later rewrites SP from a flash word. The command
# loop only needs a usable stack, and the top of SRAM is the region a W can reach.
INITIAL_SP = 0x10001FF8

CRP_PATTERNS = {
    "1": 0x12345678,
    "2": 0x87654321,
    "3": 0x43218765,
    "none": 0xFFFFFFFF,
}

DEFAULT_FLOOR_BASE = 0x10000100
