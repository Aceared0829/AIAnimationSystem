// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AIAnimationMotionMatchingPrepareCommandlet.generated.h"

/** 复制插件原 AnimBP 并在新副本的最终输出前插入在线模型姿态节点。 */
UCLASS()
class AIANIMATIONMOTIONMATCHINGEDITOR_API UAIAnimationMotionMatchingPrepareCommandlet final : public UCommandlet
{
	GENERATED_BODY()

public:
	UAIAnimationMotionMatchingPrepareCommandlet();
	virtual int32 Main(const FString& Params) override;
};
