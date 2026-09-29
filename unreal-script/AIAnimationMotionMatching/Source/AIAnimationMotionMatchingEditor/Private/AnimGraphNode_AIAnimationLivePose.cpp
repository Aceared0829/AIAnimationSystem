// Copyright ZhaoZining. All Rights Reserved.

#include "AnimGraphNode_AIAnimationLivePose.h"

#define LOCTEXT_NAMESPACE "AIAnimationMotionMatching"

FText UAnimGraphNode_AIAnimationLivePose::GetNodeTitle(ENodeTitleType::Type TitleType) const
{
	return LOCTEXT("Title", "AIAnimation Live Pose");
}

FText UAnimGraphNode_AIAnimationLivePose::GetTooltipText() const
{
	return LOCTEXT("Tooltip", "在 Motion Matching 源姿态上显示因果模型输出；蹲伏、离地或模型失败时保留源姿态。Root 由 CMC 控制。");
}

FString UAnimGraphNode_AIAnimationLivePose::GetNodeCategory() const
{
	return TEXT("AI Animation");
}

#undef LOCTEXT_NAMESPACE
