// Copyright ZhaoZining. All Rights Reserved.

// 原生预览图使用实验 AnimGraph 重建节点，在真实动画任务中采集结果。
#include "AIAnimationPreviewInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNode_SequencePlayer.h"
#include "Animation/AnimSequence.h"

class FAIAnimationPreviewProxy final : public FAnimInstanceProxy
{
public:
	explicit FAIAnimationPreviewProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance) {}

	virtual FAnimNode_Base* GetCustomRootNode() override { return &Reconstruction; }
	virtual void GetCustomNodes(TArray<FAnimNode_Base*>& OutNodes) override
	{
		OutNodes.Add(&Reconstruction);
	}

	virtual void Initialize(UAnimInstance* Instance) override
	{
		UAIAnimationPreviewInstance* Preview = CastChecked<UAIAnimationPreviewInstance>(Instance);
		Player.SetSequence(Preview->Sequence);
		Player.SetLoopAnimation(Preview->bLoopAnimation);
		PreviousAssetTime = -1.0f;
		Reconstruction.Source.SetLinkNode(&Player);
		Reconstruction.Model = Preview->ReconstructionModel;
		Reconstruction.bEnabled = Preview->bReconstruct || Preview->bReferenceOnly;
		Reconstruction.bReferenceOnly = Preview->bReferenceOnly;
		Reconstruction.bAllowGameThreadInference = Preview->bAllowGameThreadInference;
		Reconstruction.HardReferenceFrames = Preview->HardReferenceFrames;
		Player.SetPlayRate(Preview->bPaused ? 0.0f : Preview->PlaybackRate);
		FAnimInstanceProxy::Initialize(Instance);
	}

	virtual void PreUpdate(UAnimInstance* Instance, float DeltaSeconds) override
	{
		UAIAnimationPreviewInstance* Preview = CastChecked<UAIAnimationPreviewInstance>(Instance);
		Player.SetSequence(Preview->Sequence);
		Player.SetLoopAnimation(Preview->bLoopAnimation);
		Reconstruction.Model = Preview->ReconstructionModel;
		Reconstruction.bEnabled = Preview->bReconstruct || Preview->bReferenceOnly;
		Reconstruction.bReferenceOnly = Preview->bReferenceOnly;
		Reconstruction.HardReferenceFrames = Preview->HardReferenceFrames;
		Player.SetPlayRate(Preview->bPaused ? 0.0f : Preview->PlaybackRate);
		if (Preview->RequestedAssetTimeSeconds >= 0.0f)
		{
			Player.SetAccumulatedTime(Preview->RequestedAssetTimeSeconds);
			PreviousAssetTime = -1.0f;
			Reconstruction.ResetSamplingHistory();
			Preview->RequestedAssetTimeSeconds = -1.0f;
		}
		// 自定义根节点也必须登记，基类才会在 Game Thread 调用其 PreUpdate。
		FAnimInstanceProxy::PreUpdate(Instance, DeltaSeconds);
	}

	virtual bool Evaluate(FPoseContext& Output) override
	{
		const float AssetTime = Player.GetCurrentAssetTime();
		if (PreviousAssetTime >= 0.0f && AssetTime < PreviousAssetTime)
		{
			Reconstruction.ResetSamplingHistory();
			PreviousAssetTime = -1.0f;
		}
		Reconstruction.SetSourceAssetTime(AssetTime, PreviousAssetTime);
		PreviousAssetTime = AssetTime;
		Reconstruction.Evaluate_AnyThread(Output);
		// 对照台固定 Root，避免长距离源轨迹走出镜头；身体相对姿态和重建输入不变。
		Output.Pose[FCompactPoseBoneIndex(0)] = Output.Pose.GetBoneContainer().GetRefPoseTransform(FCompactPoseBoneIndex(0));
		return true;
	}

	virtual void PostEvaluate(UAnimInstance* Instance) override
	{
		FAnimInstanceProxy::PostEvaluate(Instance);
		UAIAnimationPreviewInstance* Preview = CastChecked<UAIAnimationPreviewInstance>(Instance);
		Preview->EvaluationStats = Reconstruction.GetStats();
		Preview->CurrentAssetTimeSeconds = Player.GetCurrentAssetTime();
	}

private:
	float PreviousAssetTime = -1.0f;
	FAnimNode_SequencePlayer_Standalone Player;
	FAnimNode_AIAnimation Reconstruction;
};

UAIAnimationPreviewInstance::UAIAnimationPreviewInstance()
{
	bUseMultiThreadedAnimationUpdate = true;
	RootMotionMode = ERootMotionMode::IgnoreRootMotion;
}

FAnimInstanceProxy* UAIAnimationPreviewInstance::CreateAnimInstanceProxy()
{
	return new FAIAnimationPreviewProxy(this);
}

void UAIAnimationPreviewInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
	delete InProxy;
}
