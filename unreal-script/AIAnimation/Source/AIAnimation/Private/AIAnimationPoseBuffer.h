// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

/** 同一段动作的一个固定采样时刻；姿态都是父骨骼局部空间，骨盆相对 Root。 */
struct FAIAnimationBufferedPose
{
	int64 Index = 0;
	TArray<FTransform> Source;
	TArray<FTransform> Model;
	double Weight = 0.0;
	int32 StationarySamples = 0;
	int32 ResumeSamples = 0;
};

/** 动画任务独占的有界播放缓冲。索引为 30 Hz 采样编号，重置后不得混入前一段动作。 */
class FAIAnimationPoseBuffer
{
public:
	/** 清空当前时间段，包括已播放边界。 */
	void Reset();
	/** 追加连续编号的源姿态，调用方保证局部骨骼顺序一致。 */
	void AddSource(int64 Index, TConstArrayView<FTransform> Pose);
	/** 合并按帧平铺的局部模型输出；已播放或曾用于插值的端点不再修改。 */
	void MergeWindow(int64 Start, int32 WindowFrames, int32 NumBones, TConstArrayView<FTransform> Poses);
	/** 按小数采样编号插值。缺模型时返回源姿态；缺时间点返回 false，OutPose 保持不变。 */
	bool Read(double Position, bool bSourceOnly, double ModelAlpha, TArray<FTransform>& OutPose, bool& bOutModelReady) const;
	/** 源骨架连续六个采样间隔静止时锁定预测；恢复动作的四个采样点逐步释放，不改已使用端点。 */
	void StabilizeStationary(double Position);
	/** 冻结当前插值的左右端点；只保留所需历史与尚未播放的输出。 */
	void Commit(double Position);
	/** 返回当前时间段的只读样本；修改缓冲后指针可能失效。 */
	const FAIAnimationBufferedPose* Find(int64 Index) const;
	int32 Num() const { return Frames.Num(); }

private:
	TArray<FAIAnimationBufferedPose> Frames;
	int64 FrozenThrough = -1;
};
