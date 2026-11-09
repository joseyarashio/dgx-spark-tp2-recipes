#!/bin/bash
# Hermes cron (no_agent): post the post-reboot verification report once, then archive it.
F=/home/joseyarashio/.cache/spark-reboot-verify/deliver.md
[ -s "$F" ] || exit 0
cat "$F"
mv "$F" "/home/joseyarashio/.cache/spark-reboot-verify/delivered_$(date +%Y%m%d_%H%M%S).md"
