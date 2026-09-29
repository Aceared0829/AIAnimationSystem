// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "AIAnimationPlayableTest.h"
#include "MotionMatchingInCpp/CommonGameplay/Player/PlayerCharacter.h"
#include "AIAnimationMotionMatchingCharacter.generated.h"

class UAIAnimationLivePoseComponent;

/** 插件玩家角色原有输入与 CMC 继续运行，动画蓝图只切换显示源姿态或模型姿态。 */
UCLASS()
class AIANIMATIONMOTIONMATCHING_API AAIAnimationMotionMatchingCharacter final : public APlayerCharacter
{
	GENERATED_BODY()

public:
	AAIAnimationMotionMatchingCharacter();

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

private:
	void ShowMotionMatching();
	void ShowControlModel();
	void ShowSpeedPhaseModel();
	void ResetTest();
	void QuitTest();

	UPROPERTY(VisibleAnywhere, Category = "AI Animation")
	TObjectPtr<UAIAnimationLivePoseComponent> LivePose;
	float ProbeSeconds = 0.0f;
	int32 LastProbeSecond = INDEX_NONE;
	bool bAutoProbe = false;
	bool bTrajectoryProbe = false;
	bool bProbeCrouched = false;
	float TraceRemainderSeconds = 0.0f;
	int32 TraceSample = 0;
	FString Trace;
};

/** 沿用实验场地，只替换 Pawn 与控制器为 MotionMatchingInCpp 的角色链路。 */
UCLASS()
class AIANIMATIONMOTIONMATCHING_API AAIAnimationMotionMatchingGameMode final : public AAIAnimationPlayableGameMode
{
	GENERATED_BODY()

public:
	AAIAnimationMotionMatchingGameMode();
};
