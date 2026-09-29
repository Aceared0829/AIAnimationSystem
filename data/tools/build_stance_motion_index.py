"""从来源动作与显式站蹲标注构建独立 v2 条件窗口。"""

import argparse
import json

from data.runtime.stance_motion import build_stance_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-contract", required=True, help="v1 条件契约目录")
    parser.add_argument("--annotations", required=True, help="经来源哈希绑定的站蹲标注 JSON")
    parser.add_argument("--output", required=True, help="尚不存在的 v2 输出目录")
    args = parser.parse_args()
    result = build_stance_index(args.base_contract, args.annotations, args.output)
    print(json.dumps({"window_split_counts": result["window_split_counts"],
                      "future_transition_window_split_counts": result["future_transition_window_split_counts"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
