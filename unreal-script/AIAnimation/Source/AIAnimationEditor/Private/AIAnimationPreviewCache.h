// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

/** 一次推理中一个可见输出帧的三路组件空间骨骼姿态。 */
struct FAIAnimationCachedFrame
{
	float SourceTimeSeconds = 0.0f;
	TArray<FTransform> BoneComponent[3];
	double InferenceMs = 0.0;
	double JointErrorCm = 0.0;
	uint64 NumInferences = 0;
	uint64 NumQualitySamples = 0;

	void Serialize(FArchive& Archive);
};

/** 编辑器预览缓存；完整的一次结果以版本化文件保存在项目 Saved 下。 */
class FAIAnimationPreviewCache
{
public:
	FString Key;
	TArray<FAIAnimationCachedFrame> Frames;

	void Reset(const FString& InKey);
	bool Load(const FString& AnimationPath, const FString& ExpectedKey, int32 ExpectedBoneCount);
	bool Save(const FString& AnimationPath) const;

private:
	static FString CachePath(const FString& AnimationPath);
};
