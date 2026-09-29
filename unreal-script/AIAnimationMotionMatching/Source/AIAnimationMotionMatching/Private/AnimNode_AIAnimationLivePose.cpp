// Copyright ZhaoZining. All Rights Reserved.

#include "AnimNode_AIAnimationLivePose.h"
#include "AIAnimationLivePoseComponent.h"
#include "Animation/AnimInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"

void FAnimNode_AIAnimationLivePose::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
	FAnimNode_Base::Initialize_AnyThread(Context);
	Source.Initialize(Context);
	bMapped = false;
	RootBoneIndex = FCompactPoseBoneIndex(INDEX_NONE);
}

void FAnimNode_AIAnimationLivePose::CacheBones_AnyThread(const FAnimationCacheBonesContext& Context)
{
	Source.CacheBones(Context);
	bMapped = false;
	RootBoneIndex = FCompactPoseBoneIndex(INDEX_NONE);
}

void FAnimNode_AIAnimationLivePose::PreUpdate(const UAnimInstance* InAnimInstance)
{
	bUseModel = false;
	const ACharacter* Character = Cast<ACharacter>(InAnimInstance->GetOwningActor());
	if (!Character || !Character->GetCharacterMovement() || Character->GetCharacterMovement()->IsCrouching()
		|| !Character->GetCharacterMovement()->IsMovingOnGround())
	{
		return;
	}
	const UAIAnimationLivePoseComponent* Component = Character->FindComponentByClass<UAIAnimationLivePoseComponent>();
	if (Component && Component->GetDisplayMode() != LastObservedMode)
	{
		LastObservedMode = Component->GetDisplayMode();
		bLoggedModelApplication = false;
		UE_LOG(LogTemp, Display, TEXT("AIAnimationLivePoseNode: requested mode=%d"), LastObservedMode);
	}
	TArray<FName> NewBoneNames;
	TArray<FTransform> NewLocalPose;
	if (!Component || !Component->CopyLatestPose(NewBoneNames, NewLocalPose))
	{
		return;
	}
	if (BoneNames != NewBoneNames)
	{
		bMapped = false;
	}
	BoneNames = MoveTemp(NewBoneNames);
	LocalPose = MoveTemp(NewLocalPose);
	bUseModel = true;
}

void FAnimNode_AIAnimationLivePose::Update_AnyThread(const FAnimationUpdateContext& Context)
{
	GetEvaluateGraphExposedInputs().Execute(Context);
	Source.Update(Context);
}

void FAnimNode_AIAnimationLivePose::Evaluate_AnyThread(FPoseContext& Output)
{
	Source.Evaluate(Output);
	if (!bUseModel || BoneNames.Num() != LocalPose.Num() || BoneNames.IsEmpty())
	{
		return;
	}
	const FBoneContainer& RequiredBones = Output.Pose.GetBoneContainer();
	if (!bMapped)
	{
		FBoneReference RootReference;
		RootReference.BoneName = TEXT("root");
		RootReference.Initialize(RequiredBones);
		if (!RootReference.IsValidToEvaluate(RequiredBones))
		{
			return;
		}
		RootBoneIndex = RootReference.GetCompactPoseIndex(RequiredBones);
		BoneIndices.Reset();
		for (const FName& Name : BoneNames)
		{
			FBoneReference Reference;
			Reference.BoneName = Name;
			Reference.Initialize(RequiredBones);
			if (!Reference.IsValidToEvaluate(RequiredBones))
			{
				BoneIndices.Reset();
				return;
			}
			BoneIndices.Add(Reference.GetCompactPoseIndex(RequiredBones));
		}
		bMapped = true;
	}
	// 重置源图的 OffsetRoot；插件 Mesh 的 -90 度旋转负责对齐模型骨架正面与 Actor 前方。
	FTransform Root = RequiredBones.GetRefPoseTransform(RootBoneIndex);
	if (!bLoggedModelApplication)
	{
		UE_LOG(LogTemp, Display, TEXT("AIAnimationPoseBasis: source_root=%s ref_root=%s model_root=%s model_pelvis=%s"),
			*Output.Pose[RootBoneIndex].ToString(), *RequiredBones.GetRefPoseTransform(RootBoneIndex).ToString(),
			*Root.ToString(), *LocalPose[0].ToString());
	}
	Output.Pose[RootBoneIndex] = Root;
	for (int32 Index = 0; Index < BoneIndices.Num(); ++Index)
	{
		FTransform& Bone = Output.Pose[BoneIndices[Index]];
		const FVector Scale = Bone.GetScale3D();
		Bone = LocalPose[Index];
		Bone.SetScale3D(Scale);
	}
	if (!bLoggedModelApplication)
	{
		bLoggedModelApplication = true;
		UE_LOG(LogTemp, Display, TEXT("AIAnimationLivePoseNode: applied %d model bones over Motion Matching source"), BoneIndices.Num());
	}
}

void FAnimNode_AIAnimationLivePose::GatherDebugData(FNodeDebugData& DebugData)
{
	DebugData.AddDebugItem(TEXT("AIAnimation Live Model Pose / MotionMatching Source"));
	Source.GatherDebugData(DebugData);
}
