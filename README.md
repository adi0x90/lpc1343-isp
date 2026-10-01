# lpc1343-isp

Unicorn harness for the LPC1343 boot ROM ISP command loop.

The boot ROM image is not in this repository. Pass it with `-rom`. The harness maps user flash, SRAM, and the boot ROM, plants the CRP word (flash `0x2FC` and the runtime copy at `0x10000184`) and the floor word at flash `0x438`, and fills the ISP pointer table. It also plants the SRAM window the address parser reads from flash (`0x43C`, `0x460`, `0x464`), so a destination inside the 8 KiB SRAM is mapped. It starts at `isp_command_loop` (`0x1FFF0FBC`). Bytes you type are what the ROM reads from the UART. Bytes it writes to the UART are the reply.

GPL-2.0-only, because the harness links [Unicorn](https://www.unicorn-engine.org/), which is GPL-2.0.

## Setup

```bash
python3 -m venv .venv
```
Create the virtualenv, once per checkout.

```bash
. .venv/bin/activate
```
Once per shell: puts `lpc-isp` and `python` on PATH.

```bash
pip install -e .
```
Install the harness and Unicorn.

```bash
bootloader=/path/to/LPC1343_bootloader_dump.bin
```
Once per shell: the boot ROM dump. Every command below passes it as `-rom "$bootloader"`.

```bash
lpc-isp -rom "$bootloader" --crp 1
```
Start a session against that dump.

ISP addresses and counts are decimal. The harness terminates each line with CR.

The ROM answers `1` to any first byte it does not implement: `?`, `h` and lowercase letters are not commands. It accepts `A`, `B`, `C`, `E`, `G`, `I`, `J`, `K`, `M`, `N`, `P`, `R`, `T`, `U`, `W` (uppercase only). Under `--crp 1` the gate refuses `R`, `T`, `G` and `M` with `19` before they reach their handler, so the demo below uses `W`.

At the `isp>` prompt:

```text
W 268435456 4
```

`268435456` is `0x10000000`. With `--crp 1` and the default floor word `0x10000100`, the ROM adds `0x200` and refuses this destination. The reply is `19`.

```text
W 268436224 4
```

`268436224` is `0x10000300`, the floor itself. The reply is `0`, and the ROM then waits for uuencoded data lines. `.reset` drops that transfer and starts the session again.

```bash
lpc-isp -rom "$bootloader" --crp 1 --break floor --command "W 268435456 4"
```

`--break floor` prints the address of the compare, `dest`, and `floor` when execution reaches it in the write handler, then lets the ROM print its status. The address is the bridge to Ghidra: Go To it to land on the instruction that decided the reply.

`--crp 2` and `--crp 3` reply `19` to `W` from the command gate, so the floor compare does not run. `--crp none` replies `0` for the low address: the floor test runs when the CRP word is the CRP1 pattern.

```bash
lpc-isp -rom "$bootloader" --crp 1 --floor-base 0x10000000 --break floor --command "W 268435456 4"
```

`--floor-base` is the word stored at flash `0x438`. The compare uses that word plus `0x200`.

Lines handled by the harness:

| line | effect |
| --- | --- |
| `.reset` | rebuild flash, SRAM, and registers |
| `.break` | toggle the floor trace |
| `.quit` | leave |

An accepted `W` reads the following ISP lines as data and a checksum. `.reset` drops that transfer and starts the command loop again. `.quit` and `.break` stay harness commands during the transfer.

```bash
lpc-isp -rom "$bootloader" --crp 1 --command "W 268435456 4" --command "W 268436224 4"
```
Repeat `--command` to send several lines in one process.

## Tests

```bash
LPC1343_ROM="$bootloader" python -m unittest discover -s tests -v
```

Without an active venv, use `.venv/bin/python` instead of `python`. The suite also looks for `../LPC-ROP/LPC1343_bootloader_dump.bin` beside this directory. ROM tests are skipped when neither is present. The image is only an argument; do not commit it.

## Docker

```bash
docker build -t lpc1343-isp .
```
Build the image. It does not contain a boot ROM.

```bash
docker run --rm -it -v "$(dirname "$bootloader")":/rom:ro lpc1343-isp -rom "/rom/$(basename "$bootloader")" --crp 1
```
Mount the dump's directory read-only at `/rom` and pass the dump inside it.

## Copyright

Copyright (C) 2026 Aditya Gupta. See [LICENSE](LICENSE).
