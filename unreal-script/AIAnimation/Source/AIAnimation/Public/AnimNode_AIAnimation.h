// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNodeBase.h"
#include "BoneContainer.h"
#include "AnimNode_AIAnimation.generated.h"

class UAIAnimationModel;
class FAIAnimationGpuSession;
class FAIAnimationPoseBuffer;

/** 动画求值的诊断快照；在动画同步点读取，不跨线程直接访问。 */
struct AIANIMATION_API FAIAnimationEvaluationStats
{
	uint64 NumInferences = 0;
	uint64 NumFailures = 0;
	uint64 NumGameThreadSkips = 0;
	uint64 NumFallbacks = 0;
	uint64 NumDiscontinuities = 0;
	bool bInferredThisEvaluation = false;
	uint64 NumQualitySamples = 0;
	bool bTemporalMetricValid = false;
	double LastModelAcceleration = 0.0;
	double LastSourceAcceleration = 0.0;
	double LastVelocityError = 0.0;
	double LastRotationErrorDegrees = 0.0;
	int32 DelayFrames = 0;
	int32 InferenceStride = 1;
	double LastInferenceMs = 0.0;
	double LastEvaluationMs = 0.0;
	double LastJointErrorCm = 0.0;
	uint32 LastThreadId = 0;
};

/**
 * 将源姿态的固定历史窗口送入 DirectML，在动画工作线程同步重建身体姿态。
 * Root、曲线和属性沿用源输入；缺骨、初始化失败、非有限输出和 Game Thread 求值均回退源姿态。
 * 每个节点独占模型实例和缓冲，不能把状态共享给多个角色。模型变更仅在 PreUpdate 生效。
 */
USTRUCT(BlueprintInternalUseOnly)
struct AIANIMATION_API FAnimNode_AIAnimation : public FAnimNode_Base
{
	GENERATED_BODY()

	/** GASP 或其他动画图提供的本地空间源姿态。 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Links")
	FPoseLink Source;

	/** 与当前 Mesh 参考骨架匹配的 Schema v2 模型。 */
	UPROPERTY(EditAnywhere, Category = "Model")
	TObjectPtr<UAIAnimationModel> Model;

	/** 是否启用重建；关闭后清空历史并输出源姿态。 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Settings", meta = (PinShownByDefault))
	bool bEnabled = true;

	/** 重建姿态的混合权重，0 为源姿态，1 为完整重建。 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Settings", meta = (PinShownByDefault, ClampMin = "0", ClampMax = "1"))
	float Alpha = 1.0f;

	/** 对照台左侧仅执行相同的延迟采样，不创建 GPU 推理实例。初始化前设置。 */
	bool bReferenceOnly = false;

	virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
	virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
	virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
	virtual void Evaluate_AnyThread(FPoseContext& Output) override;
	virtual bool HasPreUpdate() const override { return true; }
	virtual void PreUpdate(const UAnimInstance* InAnimInstance) override;
	virtual void GatherDebugData(FNodeDebugData& DebugData) override;

	/** 返回本节点快照；仅允许动画任务完成后的同步点调用。 */
	const FAIAnimationEvaluationStats& GetStats() const { return Stats; }

	/** 动画任务内在源时间回绕时调用，丢弃跨断点历史并重新预热。 */
	void ResetSamplingHistory();

private:
	bool MapBones(const FBoneContainer& RequiredBones);
	void ResetHistory();
	bool InferWindow(int64 LastSample);
	void MeasureQuality(int64 SampleIndex);
	void ToLocal(TConstArrayView<FTransform> Component, TArray<FTransform>& Local) const;
	void ToPositions(TConstArrayView<FTransform> Local, TArray<FVector>& Positions) const;
	TSharedPtr<FAIAnimationPoseBuffer> Playback;
	TArray<FTransform> LastDisplayed;
	TArray<FTransform> TransitionFrom;
	TArray<FVector> PreviousModelPositions;
	TArray<FVector> OlderModelPositions;
	TArray<FVector> PreviousSourcePositions;
	TArray<FVector> OlderSourcePositions;
	int64 LastQualityIndex = -1;
	int64 SampleIndex = -1;
	double ModelBlend = 0.0;
	double TransitionSeconds = 1.0;
	bool bStreaming = true;
	bool bLoadedReferenceOnly = false;
	int32 ActiveDelayFrames = 8;
	TSharedPtr<FAIAnimationGpuSession> Session;
	TWeakObjectPtr<UAIAnimationModel> LoadedModel;
	TArray<FCompactPoseBoneIndex> BoneIndices;
	FCompactPoseBoneIndex RootIndex;
	TArray<float> History;
	FAIAnimationEvaluationStats Stats;
	double AccumulatedSeconds = 0.0;
	double SampleRemainderSeconds = 0.0;
	TArray<FTransform> PreviousSourcePose;
	bool bHasPreviousSourcePose = false;
	int32 NumHistoryFrames = 0;
	bool bMapped = false;
	bool bResetRequested = false;
	FVector PreviousWorldLocation = FVector::ZeroVector;
	bool bHasWorldLocation = false;
};
