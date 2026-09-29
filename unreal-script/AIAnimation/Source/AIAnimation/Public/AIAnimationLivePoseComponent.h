// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "AIAnimationLivePoseComponent.generated.h"

struct FAIAnimationPlayableRuntime;

/**
 * 在 CMC 更新后用已执行的 Root 与当前速度生成姿态，供动画图在 PreUpdate 拷贝。
 * 组件不改 Actor 位移；模型无蹲伏条件，蹲伏时动画图必须使用源姿态。
 */
UCLASS(ClassGroup = (AIAnimation), meta = (BlueprintSpawnableComponent))
class AIANIMATION_API UAIAnimationLivePoseComponent final : public UActorComponent
{
	GENERATED_BODY()

public:
	UAIAnimationLivePoseComponent();
	virtual ~UAIAnimationLivePoseComponent() override;

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** 0 为原 Motion Matching，1 为对照模型，2 为速度/阶段模型。 */
	void SetDisplayMode(int32 NewMode);
	int32 GetDisplayMode() const { return DisplayMode; }
	void ResetModel();
	bool CopyLatestPose(TArray<FName>& OutBoneNames, TArray<FTransform>& OutLocalPose) const;
	bool IsModelReady() const;
	float GetLastInferenceMs() const;
	int32 GetInferenceCount() const;
	const FString& GetLastError() const;

private:
	void StepModel();

	FAIAnimationPlayableRuntime* Runtime = nullptr;
	TArray<FName> BoneNames;
	TArray<FTransform> LatestLocalPose;
	FString StartupError;
	float SampleRemainderSeconds = 0.0f;
	bool bWasModelEligible = false;
	int32 DisplayMode = 0;
	bool bHasPose = false;
};
