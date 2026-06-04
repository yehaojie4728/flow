#!/usr/bin/python3
import argparse
import os
import sys
import time

import export_uploader_topo
import probe_severity_analyzer


def file_state(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return (0, 0)


def run_once(args):
    loops = probe_severity_analyzer.parse_probe_log(args.input)
    agg_windows = probe_severity_analyzer.parse_agg_windows(args.agg_input)
    results = probe_severity_analyzer.classify_loops(
        loops,
        agg_windows,
        args.probe_bytes_mb,
        args.baseline_gbps,
        args.p2_ratio,
        args.p1_ratio,
    )
    probe_severity_analyzer.write_csv(results, args.output)
    payload = export_uploader_topo.build_payload(results, args.uploader_script)
    export_uploader_topo.write_json(payload, args.topo_output)
    print(
        f"[probe_analysis_worker] updated severity={args.output} topo={args.topo_output} "
        f"loops={len(results)}"
    )
    sys.stdout.flush()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=os.path.join(root_dir, "logs/runtime/probe.log"))
    parser.add_argument("--agg-input", default=os.path.join(root_dir, "runs/agg/aclrtMemcpy_numa_trace.log"))
    parser.add_argument("--output", default=os.path.join(root_dir, "runs/severity/probe_severity.csv"))
    parser.add_argument("--topo-output", default=os.path.join(root_dir, "runs/severity/probe_topo_payload.json"))
    parser.add_argument("--uploader-script", default="/root/uploader/upload_topo.py")
    parser.add_argument("--probe-bytes-mb", type=float, default=256.0)
    parser.add_argument("--baseline-gbps", type=float, default=25.0)
    parser.add_argument("--p2-ratio", type=float, default=0.90)
    parser.add_argument("--p1-ratio", type=float, default=0.70)
    parser.add_argument("--poll-sec", type=float, default=1.0)
    args = parser.parse_args()

    last_probe_state = None
    last_agg_state = None
    while True:
        try:
            probe_state = file_state(args.input)
            agg_state = file_state(args.agg_input)
            if probe_state != last_probe_state or agg_state != last_agg_state:
                run_once(args)
                last_probe_state = probe_state
                last_agg_state = agg_state
        except Exception as exc:
            print(f"[probe_analysis_worker] error: {exc}", file=sys.stderr)
            sys.stderr.flush()
        time.sleep(max(0.2, args.poll_sec))


if __name__ == "__main__":
    main()
