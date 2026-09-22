// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "Commandlets/Commandlet.h"
#include "AIAnimationPrepareCommandlet.generated.h"

/** 导入已验证 ONNX、复制 GASP 动画图并生成独立对照地图；只写 /Game/AIAnimationPreview。 */
UCLASS()
class UAIAnimationPrepareCommandlet final : public UCommandlet
{
	GENERATED_BODY()

public:
	UAIAnimationPrepareCommandlet();
	virtual int32 Main(const FString& Params) override;
};
