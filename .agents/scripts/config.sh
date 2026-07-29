#!/usr/bin/env bash
# Source, don't run. CONFIG.md's `- KEY = "value"` lines become variables: USER lands as
# USER_LOGIN ($USER is the shell's own), list values are skipped, anything already set wins.

_md="${CONFIG_MD:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/CONFIG.md}"

while read -r key value; do
  [ "$key" = USER ] && key=USER_LOGIN
  eval ": \${$key:=\$value}" && export "$key"
done < <(sed -nE 's/^- ([A-Z_]+)[[:space:]]*= "(.*)"[[:space:]]*$/\1 \2/p' "$_md")
