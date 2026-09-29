// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "AnimGraphNode_Base.h"
#include "AnimNode_AIAnimationLivePose.h"
#include "AnimGraphNode_AIAnimationLivePose.generated.h"

/** 接在插件原动画图最终输出前的在线模型姿态节点。 */
UCLASS()
class AIANIMATIONMOTIONMATCHINGEDITOR_API UAnimGraphNode_AIAnimationLivePose final : public UAnimGraphNode_Base
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, Category = "Settings")
	FAnimNode_AIAnimationLivePose Node;

	virtual FText GetNodeTitle(ENodeTitleType::Type TitleType) const override;
	virtual FText GetTooltipText() const override;
	virtual FString GetNodeCategory() const override;
};
