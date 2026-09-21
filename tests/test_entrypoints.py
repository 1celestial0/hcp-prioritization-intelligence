from __future__ import annotations


def test_demo_and_eval_entrypoints(tmp_path):
    from demo.run_prioritization import main as demo_main
    from eval.run_eval import main as eval_main

    assert demo_main(["--audit-path", str(tmp_path / "demo.jsonl")]) == 0
    assert eval_main() == 0
