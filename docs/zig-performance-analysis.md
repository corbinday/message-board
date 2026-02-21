# SpaceOS Performance Analysis: MicroPython vs Zig

**Date:** 2026-02-21
**Scope:** `space-os/` firmware (RP2040 / Pimoroni Unicorn boards)
**Problem statement:** Display rendering and Ably MQTT polling compete for CPU on a single-threaded MicroPython runtime, causing connection instability and dropped frames.

---

## 1. The Exact Contention Problem

The RP2040 chip (Raspberry Pi Pico W) has two ARM Cortex-M0+ cores running at 133 MHz. MicroPython uses exactly **one** of them and runs everything cooperatively in a single thread. There is no preemptive scheduler.

The main loop in `app.py:815-873` runs this sequence every iteration:

```
check MQTT messages
process pending commands
check reconnect/heartbeat
poll buttons
player.tick()  →  render_frame()  →  gc.collect()   ← bottleneck
time.sleep(0.02)                                      ← 20ms blind spot
gc.collect()
```

### Where the fighting happens

**`render_frame()` (`player.py:31-76`) blocks for 10–50 ms per frame.**

For a 32×32 Cosmic Unicorn (1,024 pixels), the inner loop executes 1,024 iterations of:
```python
pen = _graphics.create_pen(r, g, b)   # Python method call + C allocation
_graphics.set_pen(pen)                 # Python method call
_graphics.pixel(x, y)                 # Python method call + bounds check
```
MicroPython bytecode interpretation adds ~3–10 µs overhead per Python-level call. With 3 calls per pixel × 1,024 pixels, that is roughly **3,000–30,000 µs (3–30 ms)** of Python dispatch overhead per frame, on top of the underlying C work.

After every frame, `gc.collect()` fires — a **stop-the-world** mark-and-sweep pause of 1–5 ms that silently suspends everything, including socket I/O.

At 10 FPS the main loop budget is 100 ms per frame. The render + GC pass alone consumes 15–50 ms, leaving **50–85 ms** for MQTT. That is survivable in isolation, but it degrades rapidly when:

- A new message arrives via Ably, triggering `_handle_content_sync()` → `play_animation()` (`player.py:159-183`). **`play_animation` is the fully blocking version** — it loops through every frame with `time.sleep(delay)` between them. For a 20-frame animation at 10 FPS, the entire MQTT receive loop is frozen for **2 seconds**.
- `_boot_sync()` downloads multiple messages sequentially (each download streams 4 KB chunks while the socket is occupied).
- Reconnect attempts (WiFi + new token + re-subscribe) run synchronously in the main loop.

### MQTT keepalive math

`ably_mqtt.py` pings every 30 s against a 60-s keepalive. If the main loop is blocked for 2+ seconds (a normal animation play), no data is lost — but missed pings stack up. Five consecutive `check_msg()` errors (`_MAX_ERRORS = 5`) mark the connection dead and trigger a 60-second reconnect wait, which is the user-visible "fighting."

---

## 2. Pimoroni C Libraries: Already at C Speed

A common misconception: the Pimoroni libraries (`cosmic`, `galactic`, `stellar`, `picographics`) **are already compiled C**, not Python. Calls to `unicorn.update(graphics)` initiate a DMA transfer to the PIO state machine at full hardware speed. The bottleneck is not inside these libraries.

The bottleneck is the **Python-level preparation loop** that calls `graphics.pixel()` once per pixel from Python. The C function receives control for each of those 1,024 individual calls, but the per-call overhead of crossing the Python/C boundary is paid 1,024 times.

**Simply importing Pimoroni's C libraries does not fix this.** The Python loop around them is what is slow.

---

## 3. Quantitative Performance Estimates

### Pixel rendering (hot path)

| Implementation | Per-pixel cost | 1,024-pixel 32×32 frame | GC pause | Total per frame |
|---|---|---|---|---|
| MicroPython (current) | ~3–10 µs Python dispatch | 3–10 ms | 1–5 ms | **4–15 ms** |
| MicroPython + bulk blit (C module) | ~0.01 µs (memcpy) | ~10 µs | none | **~0.1 ms** |
| Zig (bare metal / Pico SDK) | ~1–5 ns | ~5 µs | none (no GC) | **~0.05 ms** |
| Zig calling Pimoroni C SDK | ~1–5 ns prep + DMA | ~5 µs | none | **~0.05 ms** |

Zig renders the same frame **100–300× faster** than current MicroPython. But the Pimoroni C bulk blit approach gets within 2× of Zig for this specific operation, with far less migration cost.

### MQTT polling budget per second

| Scenario | Time available for MQTT per second |
|---|---|
| Current MicroPython (10 FPS) | ~500 ms (rest taken by rendering + GC + 20ms sleeps) |
| Current MicroPython during play_animation | **~0 ms** (fully blocked) |
| With bulk blit C module | ~980 ms |
| Zig on core 0, MQTT on core 1 | **1,000 ms (independent core)** |

---

## 4. Feasibility: Switching to Zig

### What Zig gives you

1. **True dual-core**: Zig + Pico SDK can launch rendering on core 0 and network I/O on core 1, which completely eliminates the scheduling conflict. This is the RP2040's biggest advantage and MicroPython cannot use it.
2. **Zero GC pauses**: Zig is garbage-collector-free. Memory is managed via stack, arena, or explicit allocation.
3. **Predictable frame timing**: Frame rendering completes in microseconds, making 60 FPS trivial and leaving the network stack idle 99% of the time.
4. **Direct C interop**: Zig's `@cImport` makes linking Pimoroni's C SDK (or the Pico SDK) straightforward. You keep the same hardware drivers.
5. **Comptime**: Zig's compile-time evaluation can bake frame data and lookup tables at build time, eliminating runtime overhead for fixed content.

### What you lose / must reimplement

| MicroPython module | Zig equivalent | Effort |
|---|---|---|
| `umqtt.simple` | No direct equivalent — implement MQTT 3.1.1 in Zig or link `paho.mqtt.c` | Medium–High |
| `urequests` / `ssl` | Pico SDK `tcp`, `mbedTLS` (already in Pico W SDK) | Medium |
| `ujson` | Zig's `std.json` (stable, fast) | Low |
| `uos`, `LittleFS` | `lfs2` C library (same one MicroPython uses) via `@cImport` | Low |
| `ntptime` | SNTP implementation (~100 lines) or Pico SDK | Low |
| OTA update / Ed25519 | Zig `std.crypto.sign.Ed25519` (in stdlib) | Low |
| REPL / live editing | None — full rebuild required for any change | High operational cost |

The main investment is the MQTT client and HTTP/TLS. The Pico W SDK includes `mbedTLS` and `lwIP`, so TLS and TCP are available — they just need wrapping. An existing C MQTT library (`coreMQTT` from AWS, `mosquitto`, or `paho-mqtt-c`) can be linked directly from Zig.

### Realistic development scope

A full Zig rewrite to reach feature parity with current SpaceOS (WiFi, MQTT/TLS, HTTP, LittleFS, OTA, Ed25519, dual-core rendering, button handling) is a **substantial engineering project** — call it 6–10 weeks of focused embedded systems work for someone already familiar with Zig and the Pico SDK.

A partial Zig approach (Zig handles core 0 display, MicroPython handles core 1 network) is **not feasible** — you cannot mix two runtimes on the same RP2040 in this way. It is one or the other.

---

## 5. The Middle Path: MicroPython + Native C Module

The actual root cause of the contention is identifiable and fixable without abandoning MicroPython. The two surgical changes are:

### Fix A — Remove `gc.collect()` from `render_frame()`

`player.py:76` calls `gc.collect()` after **every rendered frame**. The main loop already collects at `app.py:873`. Collecting inside the render function adds 1–5 ms of stop-the-world GC 10 times per second for no benefit. Remove it.

### Fix B — Never call `play_animation()` from the main path

`player.py:159-183` is the blocking animation player. It is called in `_handle_content_sync()` (`app.py:537-543`) when a new inbox message arrives. During this call, MQTT is deaf for the full animation duration.

Switch to `start_animation()` and let `tick()` in the main loop advance frames non-blocking. The read receipt callback must then be attached to the `on_loop_complete` mechanism already present in `tick()` / `loop_count()`.

These two changes alone are likely to resolve the reported contention without any C or Zig work.

### Fix C — Native C module for bulk pixel blit (optional enhancement)

If rendering speed remains a concern after A+B, write a small native MicroPython module in C:

```c
// mp_bulk_blit(pixel_data, width, height, frame_index, gfx_obj)
// Copies one frame of RGB888 bytes into PicoGraphics framebuffer via
// a single C-level loop — ~100x faster than Python pixel()
```

Pimoroni's `PicoGraphics` object is accessible from C via the MicroPython C API. This module stays inside MicroPython but eliminates the Python-level per-pixel loop overhead, reducing frame time from ~15 ms to ~0.1 ms. The rest of SpaceOS stays in Python unchanged.

This option requires building a custom MicroPython firmware with the blit module included, which is a build-system task rather than a logic rewrite.

---

## 6. Decision Matrix

| Option | Contention fixed? | Rendering speed | Dev effort | Risk |
|---|---|---|---|---|
| A+B: Remove render GC + fix blocking animation | Yes (for typical cases) | Same | **Hours** | Very low |
| A+B + C: Add C blit module | Yes | ~100× faster | Days–1 week | Low |
| Full Zig rewrite | Yes (dual-core) | ~200× faster | Weeks–months | High |
| Keep as-is | No | Baseline | None | Ongoing instability |

---

## 7. Recommendation

**Do A+B first.** The `gc.collect()` inside `render_frame()` and the blocking `play_animation()` call during message sync are the two identified causes of MQTT starvation. Both are removable without changing the overall architecture. This is low-risk and can be validated immediately.

**Do C if needed.** If frame rendering still takes up an unacceptable share of the loop budget (measurable by adding `time.ticks_ms()` instrumentation around `player.tick()`), add the native C blit module. This keeps the entire SpaceOS codebase in Python while eliminating the main hotspot.

**Consider Zig only if** the project outgrows the RP2040's single-core budget — for example, if higher frame rates, complex real-time effects, or stricter MQTT latency guarantees are needed. At that point, the dual-core architecture is the genuine differentiator, and the Pico SDK + Zig (calling Pimoroni's C libraries directly) is the right path. The existing Space Pack binary format, LittleFS storage layout, and Ably MQTT protocol can all be preserved — only the runtime changes.

**Rewriting Pimoroni's C libraries in Zig adds no value.** Those libraries are already at native speed. The gain from Zig comes from eliminating MicroPython's per-call overhead around those libraries and from using the second core — not from faster underlying LED drivers.
