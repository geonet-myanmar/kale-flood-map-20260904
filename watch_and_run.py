#!/usr/bin/env python3
"""
Wait for the post-flood Sentinel-1 scene to reach Earth Engine, then run
flood_mapping.py automatically.

WHY THIS EXISTS
  2026-08-17 is the scheduled DESCENDING track-106 repeat over this AOI, but
  Earth Engine ingests a pass hours after acquisition and not in acquisition
  order.  Rather than re-running --check by hand, this polls the catalogue and
  starts the full native-resolution run the moment the scene is usable.

WHAT COUNTS AS "USABLE"  (both must hold, in the SAME collection)
  * both dates present on the configured pass/track, and
  * post-flood AOI coverage >= MIN_COVERAGE, and
  * the post-flood scene count is UNCHANGED from the previous poll.

  The last two matter.  Ingestion of one pass is not atomic: the first scene of
  a three-scene pass can appear alone, covering a third of the AOI.  Launching
  then would map a third of the flood and silently report the rest as dry.  So
  a full-coverage sighting has to survive one more poll before the run starts.

  Collection choice is left to flood_mapping.choose_collection(), which prefers
  COPERNICUS/S1_GRD and falls back to S1_GRD_FLOAT (linear power, ingested
  earlier, exactly 10*log10-convertible).  Whichever is picked supplies BOTH
  composites -- the pair is never split across collections.

NOTHING IS SUBSTITUTED
  This only ever waits for the dates configured in flood_mapping.py.  If the
  pass is missed entirely, the next track-106 opportunity is 12 days later and
  this script gives up at DEADLINE_HOURS rather than quietly using another date.

USAGE
    python watch_and_run.py                 # poll, then run
    python watch_and_run.py --once          # single availability check
    python watch_and_run.py --interval 300  # poll every 5 minutes
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import flood_mapping as F

POLL_SECONDS   = 600      # 10 minutes -- a metadata query, cheap to repeat
DEADLINE_HOURS = 14       # give up rather than poll forever
LOG            = "watch_and_run.log"

# Deliberately the SAME constant flood_mapping.choose_collection() applies.
# When they differed, this watcher launched on S1_GRD_FLOAT at 100% while the
# run then independently picked S1_GRD at 94.7% -- the gate has to be one
# number, or the thing that waits and the thing that chooses can disagree.
MIN_COVERAGE = F.MIN_AOI_COVERAGE


def say(msg: str) -> None:
    """Print with a UTC stamp, to the console and to LOG."""
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def probe(aoi) -> tuple:
    """
    One availability sweep.

    Returns (cid, is_linear, n_post, cov_post) for the first collection holding
    both dates with enough coverage, or (None, None, n_post, cov_post) from the
    best collection seen, so the caller can log progress while waiting.
    """
    best = (0, 0.0)
    for cid, is_linear in F.S1_COLLECTIONS:
        n_pre, cov_pre = F.s1_availability(
            aoi, F.PRE_FLOOD_DATE, F.DATE_WINDOW, F.ORBIT_PASS, F.REL_ORBIT, cid)
        n_post, cov_post = F.s1_availability(
            aoi, F.POST_FLOOD_DATE, F.DATE_WINDOW, F.ORBIT_PASS, F.REL_ORBIT, cid)
        if (n_post, cov_post) > best:
            best = (n_post, cov_post)
        if n_pre and n_post and cov_pre >= MIN_COVERAGE and cov_post >= MIN_COVERAGE:
            return cid, is_linear, n_post, cov_post
    return None, None, best[0], best[1]


def launch() -> int:
    """Run flood_mapping.py in this interpreter, streaming its output to LOG."""
    say("Scene is in. Starting the full native-resolution run "
        "(expect 1-3 hours: ~100 download tiles at 10 m).")
    cmd = [sys.executable, "-u", "flood_mapping.py"]
    with open(LOG, "a", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace",
                                bufsize=1, env={**os.environ,
                                                "PYTHONIOENCODING": "utf-8"})
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            fh.write(line)
        rc = proc.wait()

    if rc == 0:
        say(f"DONE. {F.OUTPUT_HTML} and {F.STATS_JSON} written.")
    else:
        say(f"flood_mapping.py exited {rc} -- see {LOG}. Downloaded tiles are "
            f"cached in {F.TEMP_DIR}/, so a re-run resumes rather than restarts.")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--once", action="store_true",
                    help="check once and exit; do not poll or run")
    ap.add_argument("--interval", type=int, default=POLL_SECONDS,
                    help=f"seconds between polls (default {POLL_SECONDS})")
    ap.add_argument("--deadline", type=float, default=DEADLINE_HOURS,
                    help=f"hours to keep polling (default {DEADLINE_HOURS})")
    args = ap.parse_args()

    F.init_gee()
    aoi = F.load_aoi(F.AOI_GEOJSON)["ee_geom"]

    say(f"Watching for {F.POST_FLOOD_DATE} on {F.ORBIT_PASS} track "
        f"{F.REL_ORBIT} (pre-flood {F.PRE_FLOOD_DATE} already confirmed). "
        f"Poll every {args.interval}s, deadline {args.deadline:g} h.")

    give_up = datetime.now(timezone.utc) + timedelta(hours=args.deadline)
    last_seen = None                      # (n_post, cov rounded) from last poll
    polls = 0

    while True:
        polls += 1
        try:
            cid, is_linear, n_post, cov_post = probe(aoi)
        except Exception as exc:                       # noqa: BLE001
            # A transient Earth Engine hiccup must not end a 12-hour watch.
            say(f"poll {polls}: {type(exc).__name__}: {exc} -- retrying")
            cid, n_post, cov_post = None, -1, -1.0

        if cid:
            key = (n_post, round(cov_post, 2))
            if key == last_seen:
                say(f"poll {polls}: {cid.split('/')[-1]} has {n_post} scene(s) "
                    f"at {cov_post:.1%} coverage, unchanged since the last poll "
                    f"-- ingestion of this pass looks complete.")
                if args.once:
                    say("--once: not launching.")
                    return 0
                return launch()
            say(f"poll {polls}: {cid.split('/')[-1]} now has {n_post} scene(s) "
                f"at {cov_post:.1%} coverage. Confirming it is stable before "
                f"launching (one more poll).")
            last_seen = key
        else:
            last_seen = None
            if n_post > 0:
                say(f"poll {polls}: {F.POST_FLOOD_DATE} partially ingested -- "
                    f"{n_post} scene(s), {cov_post:.1%} of the AOI. Waiting for "
                    f"{MIN_COVERAGE:.0%}.")
            elif n_post == 0:
                say(f"poll {polls}: {F.POST_FLOOD_DATE} not in the catalogue yet.")

        if args.once:
            say("--once: exiting without launching.")
            return 1

        if datetime.now(timezone.utc) >= give_up:
            say(f"Gave up after {args.deadline:g} h and {polls} polls. "
                f"{F.POST_FLOOD_DATE} never reached {MIN_COVERAGE:.0%} coverage. "
                f"Nothing was substituted and nothing was written. Re-run this "
                f"watcher, or check whether the pass was acquired at all "
                f"(python flood_mapping.py --check).")
            return 2

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
