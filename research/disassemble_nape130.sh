#!/usr/bin/env bash
# Download and analyze one pinned server image. No HID/device operations.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output="$root/snapshots/firmware/1.3.0"
ghidra="${GHIDRA_HOME:-/opt/ghidra}"
mkdir -p "$output/ghidra"
image="$output/nape-pro-1.3.0.bin"
if [[ ! -f "$image" ]]; then
    curl --fail --location --output "$image.download" \
        'https://launcher.keychron.com/static/device/875824192/bin/01a05725-997a-74ac-befb-4673b15ba939.bin'
    mv -- "$image.download" "$image"
fi
printf '%s  %s\n' \
    'e54dd28fc8ec9bd5e4562d3fb3077ea9b40c16772453efe091c790ae2cf06a76' \
    "$image" | sha256sum --check --status
"$ghidra/support/analyzeHeadless" "$output/ghidra" Nape130v8m \
    -import "$image" -overwrite \
    -loader BinaryLoader -loader-baseAddr 0x0402d000 \
    -processor ARM:LE:32:v8-m \
    -scriptPath "$root/research/ghidra" \
    -preScript PrepareNape130.java \
    -preScript AnnotateNape130.java \
    -postScript ExportNapeAnalysis.java "$output/export" \
    -analysisTimeoutPerFile 240 -max-cpu 4 \
    > "$output/ghidra.log" 2>&1
if grep -Eq 'ERROR REPORT SCRIPT ERROR|REPORT: Analysis failed|Analysis timed out' "$output/ghidra.log"; then
    printf 'Analysis did not finish cleanly. Check %s\n' "$output/ghidra.log" >&2
    exit 1
fi
python3 "$root/research/export_nape130.py" "$output"
