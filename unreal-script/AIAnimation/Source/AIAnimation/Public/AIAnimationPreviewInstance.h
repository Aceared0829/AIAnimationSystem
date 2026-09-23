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

	/** 预览专用的原始30 Hz动画帧号；仅右侧重建角色读取。 */
	TArray<int32> HardReferenceFrames;

	/** Game Thread 同步点返回当前源动画时间，供时间轴显示。 */
	float CurrentAssetTimeSeconds = 0.0f;

	/** 预览暂停时仍可在当前时刻求值；切换动画时清空。 */
	bool bPaused = false;

	/** 源动画时间相对真实时间的倍率；慢放时序列按子帧连续取样。 */
	float PlaybackRate = 1.0f;

	/** 录制结果时停在动画末帧，留出推理延迟所需的尾部采样。 */
	bool bLoopAnimation = true;

	/** 请求跳到源动画时间；Game Thread 设置，下一次代理更新时消费。 */
	float RequestedAssetTimeSeconds = -1.0f;

	/** PostEvaluate 已同步回 Game Thread 的统计量。 */
	FAIAnimationEvaluationStats EvaluationStats;

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
};
