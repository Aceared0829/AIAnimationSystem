// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "Animation/AnimInstance.h"
#include "AnimNode_AIAnimation.h"
#include "AIAnimationPreviewInstance.generated.h"

class UAnimSequence;

/** 对照场景专用 AnimInstance；在真实动画任务中播放源动画并执行重建节点。 */
UCLASS(Transient, NotBlueprintable)
class AIANIMATION_API UAIAnimationPreviewInstance final : public UAnimInstance
{
	GENERATED_BODY()

public:
	UAIAnimationPreviewInstance();

	/** Game Thread 在首次 Tick 前设置，之后切换需要重新初始化动画。 */
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> Sequence;

	/** 仅重建角色设置，参考角色保持为空。 */
	UPROPERTY(Transient)
	TObjectPtr<UAIAnimationModel> ReconstructionModel;

	/** 用于同一场景中的基线阶段，关闭时仅播放源动画。 */
	UPROPERTY(Transient)
	bool bReconstruct = false;

	/** 左侧对照只延迟源姿态，不执行模型。 */
	bool bReferenceOnly = false;

	/** PostEvaluate 已同步回 Game Thread 的统计量。 */
	FAIAnimationEvaluationStats EvaluationStats;

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
};
