// Copyright ZhaoZining. All Rights Reserved.

// 编辑器节点只暴露配置，不持有运行时模型实例。
#include "AnimGraphNode_AIAnimation.h"

#define LOCTEXT_NAMESPACE "AIAnimation"

FText UAnimGraphNode_AIAnimation::GetNodeTitle(ENodeTitleType::Type TitleType) const
{
	return LOCTEXT("Title", "AI Animation GPU Reconstruction");
}

FText UAnimGraphNode_AIAnimation::GetTooltipText() const
{
	return LOCTEXT("Tooltip", "在动画工作线程调用 DirectML GPU，重建身体姿态；Root 与源动画属性保留。缺骨或失败时回退源姿态。");
}

FString UAnimGraphNode_AIAnimation::GetNodeCategory() const
{
	return TEXT("AI Animation");
}

#undef LOCTEXT_NAMESPACE
