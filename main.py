"""
main.py — CLI entry point for the Multi-Source Candidate Data Transformer.

This module provides the minimal command-line interface placeholder for
Phase 1.  No business logic is executed here yet.

Usage
-----
::

    python main.py --ats inputs/candidate.json --resume inputs/resume.pdf

The CLI accepts optional paths to input files and prints a confirmation that
the pipeline has been initialised.  Actual pipeline execution will be wired
in Phase 2.

Design notes
------------
* Uses ``argparse`` from the standard library — no additional CLI framework
  dependency is required for Phase 1.
* All path arguments accept strings and are converted to ``pathlib.Path``
  objects for downstream compatibility.
* The ``run()`` function is the single entry point, called by ``if __name__``
  guard at the bottom.  This makes the module importable in tests without
  side effects.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """
    Construct and return the CLI argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser with all registered arguments.
    """
    parser = argparse.ArgumentParser(
        prog="candidate-transformer",
        description=(
            "Multi-Source Candidate Data Transformer — "
            "ingest ATS JSON and résumé PDFs into a unified Candidate Profile."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --ats inputs/candidate.json --resume inputs/resume.pdf\n"
            "  python main.py --ats inputs/candidate.json\n"
        ),
    )

    parser.add_argument(
        "--ats",
        type=Path,
        metavar="PATH",
        default=None,
        help="Path to the ATS JSON input file.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        metavar="PATH",
        default=None,
        help="Path to the résumé PDF input file.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        default=Path("config/default_projection.json"),
        help=(
            "Path to the projection configuration JSON file. "
            "Defaults to config/default_projection.json."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="PATH",
        default=Path("output/candidate_profile.json"),
        help=(
            "Path for the output JSON file. "
            "Defaults to output/candidate_profile.json."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose / debug logging.",
    )

    return parser


def run(args: argparse.Namespace) -> int:
    """
    Execute the pipeline with the provided CLI arguments.

    Parameters
    ----------
    args:
        Parsed CLI arguments from :func:`build_parser`.

    Returns
    -------
    int
        Exit code: ``0`` for success, non-zero for failure.

    Notes
    -----
    Phase 1: Only prints a confirmation message.  No pipeline stages are
    executed.  Actual pipeline wiring will be introduced in Phase 2.
    """
    # ------------------------------------------------------------------
    # Phase 2+ Pipeline Execution
    # ------------------------------------------------------------------
    import json
    from src.adapters.ats_adapter import ATSAdapter
    from src.adapters.resume_adapter import ResumeAdapter
    from src.merger.merge_engine import MergeEngine
    from src.projector.projection_engine import ProjectionEngine
    from src.models.config import ProjectionConfig
    
    profiles = []
    
    if args.ats:
        print(f"[*] Parsing ATS JSON: {args.ats}")
        ats_adapter = ATSAdapter(path=args.ats)
        ats_adapter.validate_source()
        profiles.append(ats_adapter.parse())
        
    if args.resume:
        print(f"[*] Parsing Resume PDF: {args.resume}")
        res_adapter = ResumeAdapter(path=args.resume)
        res_adapter.validate_source()
        profiles.append(res_adapter.parse())
        
    if not profiles:
        print("[-] No inputs provided. Exiting.")
        return 1

    # Merge
    if len(profiles) == 1:
        print("[*] Only one source provided; skipping merge.")
        merged_profile = profiles[0]
    else:
        print("[*] Merging ATS and Resume profiles...")
        merge_result = MergeEngine().merge(profiles[0], profiles[1])
        merged_profile = merge_result.merged_profile
        
    # Project
    print(f"[*] Loading projection config: {args.config}")
    try:
        config_text = args.config.read_text(encoding="utf-8")
        proj_config = ProjectionConfig.model_validate_json(config_text)
    except FileNotFoundError:
        print(f"[-] Config file not found: {args.config}. Please create it.")
        return 1
        
    print("[*] Projecting merged profile...")
    engine = ProjectionEngine(config=proj_config)
    output_dict = engine.project(merged_profile)
    
    # Write Output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_dict, indent=2, default=str), encoding="utf-8")
    
    print(f"\n[+] Pipeline completed successfully! Output saved to: {args.output}")
    return 0

def main() -> None:
    """
    Parse CLI arguments and delegate to :func:`run`.

    This is the console-script entry point registered in ``pyproject.toml``.
    """
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
