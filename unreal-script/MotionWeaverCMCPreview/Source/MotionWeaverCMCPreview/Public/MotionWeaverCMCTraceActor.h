// Copyright ZhaoZining. All Rights Reserved.

/**
 * @file MotionWeaverCMCTraceActor.h
 * @brief 声明单机 CMC 请求状态、执行 Root 与在线估计轨迹的关卡观测器。
 */

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MotionWeaverCMCTraceActor.generated.h"

class ACharacter;

/**
 * 放在单机测试关卡中，观测第一个玩家的 CMC 状态并显示短时轨迹。
 *
 * 本 Actor 不控制玩家、不修改位移或姿态。紫色线仅用当前速度做在线外推，
 * 不是 CMC 的真实未来轨迹，也不是 MotionBricks Root 模型预测。
 * PIE 结束时将最多 18000 行观测写入项目 Saved/MotionWeaver 目录。
 * 采样名义间隔为 1/30 秒，但每个 Tick 最多取一次，低帧率下并非固定 30 Hz 数据。
 * 记录的请求是 CMC 的 bWantsToCrouch，不是原始玩家按键事件。
 * 每个 PIE World 只应放置一个实例；监听服务器及多人语义尚未实现。
 *
 * @see docs/player-state-conditioned-animation-plan.md
 */
UCLASS()
class MOTIONWEAVERCMCPREVIEW_API AMotionWeaverCMCTraceActor final : public AActor
{
	GENERATED_BODY()

public:
	AMotionWeaverCMCTraceActor();

protected:
	//~ Begin AActor Interface
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	//~ End AActor Interface

private:
	void RecordSample(const ACharacter& Character);
	void DrawTrace(const ACharacter& Character) const;
	void RunAutoTest(ACharacter& Character);
	void FinishAutoTest(bool bPassed, const TCHAR* Reason);
	void RequestTestScreenshot(const TCHAR* Name) const;
	void SaveSamples();

	TWeakObjectPtr<ACharacter> TrackedCharacter;
	TArray<FVector> RecentRootLocations;
	TArray<FString> SampleRows;
	float ElapsedSeconds = 0.0f;
	float SecondsSinceSample = 0.0f;
	float UncrouchPendingSeconds = 0.0f;
	float AutoTestPhaseStartedSeconds = 0.0f;
	float AutoTestInitialX = 0.0f;
	int32 AutoTestPhase = 0;
	bool bLastRequestedCrouch = false;
	bool bLastAcceptedCrouch = false;
	bool bAutoTest = false;
	bool bSamplesSaved = false;
};
