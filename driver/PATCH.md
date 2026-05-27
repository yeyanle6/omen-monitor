# hp-wmi patches for OMEN 16-wf0 (board 8BAB) on kernel 6.8

`hp-wmi.c` here is forked from the [omen-fan-control](https://github.com/dmidlb/omen-fan-control) upstream and adjusted to compile against the Ubuntu HWE 6.8 headers. The exact delta against `hp-wmi.c.orig` is below — show it locally with:

```bash
diff -u driver/hp-wmi.c.orig driver/hp-wmi.c
```

There are three independent compatibility fixes. Each is gated by a macro that `Makefile` writes into the generated `omen_pp_compat.h` after inspecting the running kernel's headers, so the same source builds on multiple kernel API generations.

## 1. `wmi_notify_handler` signature changed (kernel ≥ 6.5)

Old API took a parsed `union acpi_object *`. The newer API takes a raw `u32 value` and the handler is expected to call `wmi_get_event_data()` itself.

We split the original body into `hp_wmi_notify_object()` and provide two thin entry points:

- `OMEN_WMI_NOTIFY_U32` defined → `hp_wmi_notify(u32 value, void *)` fetches data via `wmi_get_event_data` and delegates.
- Otherwise → `hp_wmi_notify(union acpi_object *obj, void *)` delegates directly.

## 2. `platform_profile_cycle()` only exists in the new platform_profile API

Calling it under the legacy `platform_profile_handler` API breaks the build, so the Fn+P hotkey handler now wraps the call in `#ifdef OMEN_PP_API_NEW`.

## 3. `platform_driver.remove` return type (kernel 6.11+)

Older kernels expect `static void remove(...)`; newer ones expect `static int remove(...)`. We detect by grepping `platform_device.h` and emit either signature accordingly. The `__exit` body is unchanged otherwise; only an `if/return 0;` tail is added in the new variant.

## Why these are stable

The three macros are derived from the actual headers shipped with the running kernel (see the `omen_pp_compat.h:` target in `Makefile`), so DKMS rebuilds on a kernel upgrade pick up the right variant automatically — **as long as** the kernel keeps providing the same set of macros / function signatures. If a future kernel changes any of the three again, the build will fail loudly and this file needs an update.
