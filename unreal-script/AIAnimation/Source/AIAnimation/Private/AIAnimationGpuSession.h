// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "AIAnimationModel.h"
#include "NNERuntimeGPU.h"

/** 每节点独占的 DirectML 实例；创建在 Game Thread，Run 只能由同一节点串行调用。 */
class FAIAnimationGpuSession final
{
public:
	static TSharedPtr<FAIAnimationGpuSession> Create(const UAIAnimationModel& Asset, FString& OutError, bool bCreateInference = true);
	bool Run(TConstArrayView<float> Input, double& OutMilliseconds);

	TArray<FAIAnimationBone> Bones;
	FName RootBone;
	int32 WindowFrames = 0;
	float SampleRate = 0.0f;
	TArray<float> Output;

private:
	TSharedPtr<UE::NNE::IModelInstanceGPU> Instance;
};
