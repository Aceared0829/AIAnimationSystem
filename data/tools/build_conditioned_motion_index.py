"""无 UE 编辑器构建 Root 驱动、硬参考姿态条件动作索引。"""

import argparse

from data.runtime.conditioned_motion import build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="现有 Schema v2 prepared 数据集")
    parser.add_argument("--output", required=True, help="必须尚不存在的新索引目录")
    parser.add_argument("--history-frames", type=int, default=24)
    parser.add_argument("--future-frames", type=int, default=24)
    parser.add_argument("--stride-frames", type=int, default=4)
    parser.add_argument("--exclude-train-indices", type=int, nargs="*", default=(),
                        help="经审计确认与留出集精确重复的训练片段清单索引")
    args = parser.parse_args()
    contract = build_index(args.source, args.output, history_frames=args.history_frames,
                           future_frames=args.future_frames, stride_frames=args.stride_frames,
                           exclude_train_indices=args.exclude_train_indices,
                           progress=lambda done, total: print(f"已检查 {done}/{total} 条动作", flush=True))
    print(f"已建立 {contract['window_count']} 个真实帧窗口；"
          f"{contract['clips_without_generation_window']} 条动作仅可作为短姿态素材；"
          f"训练/验证/测试窗口 {contract['window_split_counts']}")


if __name__ == "__main__":
    main()
