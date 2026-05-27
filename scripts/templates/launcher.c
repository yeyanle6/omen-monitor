/* Tiny ELF launcher for OMEN Monitor.
 *
 * Ubuntu 22.04 GNOME/DING does not run .desktop files on double-click without
 * explicit "Allow Launching" each time, but it does run ELF binaries directly.
 * This wrapper just execs run_omen_monitor.sh; the script path is injected at
 * build time via -DSCRIPT_PATH=\"...\" so the source has no hardcoded paths.
 *
 * Build:
 *   gcc -DSCRIPT_PATH='"/abs/path/to/run_omen_monitor.sh"' launcher.c -o OMEN-Monitor
 */

#include <unistd.h>

#ifndef SCRIPT_PATH
#error "SCRIPT_PATH must be defined at build time (-DSCRIPT_PATH=\"...\")"
#endif

int main(void) {
    char *const argv[] = {
        "/bin/bash",
        SCRIPT_PATH,
        (char *)0,
    };
    execv(argv[0], argv);
    return 127;
}
