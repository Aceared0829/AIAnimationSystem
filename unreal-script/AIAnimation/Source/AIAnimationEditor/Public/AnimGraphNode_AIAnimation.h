// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "AnimGraphNode_Base.h"
#include "AnimNode_AIAnimation.h"
#include "AnimGraphNode_AIAnimation.generated.h"

/** 在动画图中插入 GPU 姿态重建，可接在 GASP 姿态与后处理之间。 */
UCLASS()
class AIANIMATIONEDITOR_API UAnimGraphNode_AIAnimation final : public UAnimGraphNode_Base
{
	GENERATED_BODY()

public:
	/** 节点配置，模型与骨架必须一致。 */
	UPROPERTY(EditAnywhere, Category = "Settings")
	FAnimNode_AIAnimation Node;

	virtual FText GetNodeTitle(ENodeTitleType::Type TitleType) const override;
	virtual FText GetTooltipText() const override;
	virtual FString GetNodeCategory() const override;
};
