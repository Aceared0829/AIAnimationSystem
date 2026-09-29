// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNodeBase.h"
#include "BoneContainer.h"
#include "AnimNode_AIAnimationLivePose.generated.h"

/** 在插件 Motion Matching 的源姿态上应用在线模型骨骼；Actor Root 仍由 CMC 管理。 */
USTRUCT(BlueprintInternalUseOnly)
struct AIANIMATIONMOTIONMATCHING_API FAnimNode_AIAnimationLivePose : public FAnimNode_Base
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Links")
	FPoseLink Source;

	virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
	virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
	virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
	virtual void Evaluate_AnyThread(FPoseContext& Output) override;
	virtual bool HasPreUpdate() const override { return true; }
	virtual void PreUpdate(const UAnimInstance* InAnimInstance) override;
	virtual void GatherDebugData(FNodeDebugData& DebugData) override;

private:
	TArray<FName> BoneNames;
	TArray<FTransform> LocalPose;
	TArray<FCompactPoseBoneIndex> BoneIndices;
	FCompactPoseBoneIndex RootBoneIndex;
	bool bUseModel = false;
	bool bMapped = false;
	bool bLoggedModelApplication = false;
	int32 LastObservedMode = INDEX_NONE;
};
