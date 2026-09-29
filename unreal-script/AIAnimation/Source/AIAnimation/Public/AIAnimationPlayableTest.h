// Copyright ZhaoZining. All Rights Reserved.

/**
 * @file AIAnimationPlayableTest.h
 * @brief 声明本地玩家实时操控的 CMC + 条件姿态模型诊断场景。
 *
 * 该场景只用于直接观察现有模型的起停、转向与脚滑；模型不持有角色位移，
 * 不负责多人预测、地形适配或正式游戏动画状态机。
 */

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "AIAnimationPlayableTest.generated.h"

class UCameraComponent;
class UPoseableMeshComponent;
class USpringArmComponent;
struct FAIAnimationPlayableRuntime;

/**
 * 用真实玩家输入驱动 CMC，并在 Game Thread 上以 30 Hz 运行无未来姿态参考的条件模型。
 *
 * 默认模型及对照模型从 `AIANIMATION_PLAYABLE_BUNDLE` 目录加载。缺文件、骨架不匹配或推理失败时
 * 保留来源 Idle 种子姿态并在屏幕和日志提示，不把回退画面标成模型结果。仅供单机诊断。
 * @see docs/experiments/2026-09-27-live-player-probe.md
 */
UCLASS()
class AIANIMATION_API AAIAnimationPlayableCharacter final : public ACharacter
{
	GENERATED_BODY()

public:
	AAIAnimationPlayableCharacter();
	virtual ~AAIAnimationPlayableCharacter() override;

protected:
	//~ Begin AActor Interface
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	//~ End AActor Interface

	//~ Begin APawn Interface
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	//~ End APawn Interface

private:
	void PressForward();
	void ReleaseForward();
	void PressBackward();
	void ReleaseBackward();
	void PressRight();
	void ReleaseRight();
	void PressLeft();
	void ReleaseLeft();
	void TurnMouse(float Value);
	void PressTurnLeft();
	void ReleaseTurnLeft();
	void PressTurnRight();
	void ReleaseTurnRight();
	void StartRun();
	void StopRun();
	void ToggleCrouch();
	void UseControlModel();
	void UsePilotModel();
	void ResetPlayback();
	void QuitTest();
	void StepModel();
	void ShowDiagnostics() const;

	/** 显示模型姿态的网格；胶囊及位移始终由 ACharacter/CMC 控制。 */
	UPROPERTY(VisibleAnywhere, Category = "AI Animation|Playable Test")
	TObjectPtr<UPoseableMeshComponent> PoseMesh;

	UPROPERTY(VisibleAnywhere, Category = "AI Animation|Playable Test")
	TObjectPtr<USpringArmComponent> CameraArm;

	UPROPERTY(VisibleAnywhere, Category = "AI Animation|Playable Test")
	TObjectPtr<UCameraComponent> Camera;

	FAIAnimationPlayableRuntime* Runtime = nullptr;
	float SamplingRemainderSeconds = 0.0f;
	int32 ActiveModelIndex = 0;
	bool bForward = false;
	bool bBackward = false;
	bool bRight = false;
	bool bLeft = false;
	bool bTurnLeft = false;
	bool bTurnRight = false;
};

/** 在空白地图中生成碰撞地板与观察网格，并把玩家控制交给 AAIAnimationPlayableCharacter。 */
UCLASS()
class AIANIMATION_API AAIAnimationPlayableGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AAIAnimationPlayableGameMode();

protected:
	//~ Begin AActor Interface
	virtual void StartPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	//~ End AActor Interface
};
