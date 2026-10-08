#!/bin/sh
# Regenerates shots/01..09 with the shared capture harness.
#   sh tools/shots.sh /path/to/harness/shot.mjs
#   HARNESS=/path/to/harness/shot.mjs sh tools/shots.sh
set -e
HARNESS="${1:-${HARNESS:?usage: sh tools/shots.sh /path/to/shot.mjs (or set HARNESS)}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
shot() { node "$HARNESS" --root "$ROOT" --out "$ROOT/shots" "$@"; }
READY='{"waitFor":"window.__demo && window.__demo.ready"}'
PARK='{"move":[60,860]}'

shot --steps "[$READY,{\"wait\":700},{\"shot\":\"01-arrival\"}]"
# A screenshot costs about 0.3 s, so a strip's frames are at least that far apart: the arrival
# (2.6 s) is caught at ~0.45 s steps, and the transition is played at a third of its speed.
shot --steps '[{"wait":200},{"strip":"02-intro","frames":6,"interval":150}]'
shot --query "skipIntro=1" --steps "[$READY,{\"wait\":400},{\"glide\":[[720,450],[880,290]],\"ms\":600},{\"wait\":900},{\"shot\":\"03-hover\"}]"
shot --query "skipIntro=1&slow=3" --steps "[$READY,{\"wait\":400},$PARK,{\"scroll\":100,\"times\":2,\"gap\":40},{\"strip\":\"04-transition\",\"frames\":6,\"interval\":60}]"
shot --query "skipIntro=1" --steps "[$READY,{\"wait\":400},$PARK,{\"eval\":\"window.__demo.goTo('zaychess')\"},{\"wait\":2200},{\"shot\":\"05-selected\"}]"
shot --mobile --w 390 --h 844 --dpr 2 --steps "[$READY,{\"wait\":700},{\"shot\":\"06-mobile\"}]"
shot --reduced-motion --steps "[$READY,{\"wait\":700},{\"shot\":\"07-reduced-motion\"}]"
shot --query "n=24" --steps "[$READY,{\"wait\":700},{\"shot\":\"08-n24\"}]"
shot --query "n=4" --steps "[$READY,{\"wait\":700},{\"shot\":\"09-n4\"}]"
