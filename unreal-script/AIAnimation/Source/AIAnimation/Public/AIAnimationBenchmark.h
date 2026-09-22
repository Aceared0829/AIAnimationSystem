// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "GameFramework/Actor.h"
#include "AIAnimationBenchmark.generated.h"

class UAIAnimationModel;
class UAnimSequence;
class UCameraComponent;
class USkeletalMesh;
class USkeletalMeshComponent;
class UTextRenderComponent;

/**
 * GASP 资产对照台：依次播放配置动作，记录动画线程 GPU 推理、整段求值和场景帧时间。
 * 默认交互预览持续循环；命令行 -AIAnimationBenchmarkOutput=目录 才自动写报告、截图并退出。
 * 场景固定 Root 用于观察重建，不作为 CMC 移动或条件生成验收。
 */
UCLASS()
class AIANIMATION_API AAIAnimationBenchmark final : public AActor
{
	GENERATED_BODY()

public:
	AAIAnimationBenchmark();
	virtual void Tick(float DeltaSeconds) override;

	/** 两个角色使用同一模型骨架的 Mesh。 */
	UPROPERTY(EditAnywhere, Category = "Benchmark")
	TObjectPtr<USkeletalMesh> CharacterMesh;

	/** 仅右侧角色运行此模型。 */
	UPROPERTY(EditAnywhere, Category = "Benchmark")
	TObjectPtr<UAIAnimationModel> Model;

	/** 每个动作运行六秒；建议选用留出数据中的多类动作。 */
	UPROPERTY(EditAnywhere, Category = "Benchmark")
	TArray<TObjectPtr<UAnimSequence>> Animations;

protected:
	virtual void BeginPlay() override;

private:
	void SetAnimation(int32 Index);
	void SaveReport();

	UPROPERTY(VisibleAnywhere, Category = "Preview")
	TObjectPtr<USkeletalMeshComponent> ReferenceMesh;
	UPROPERTY(VisibleAnywhere, Category = "Preview")
	TObjectPtr<USkeletalMeshComponent> ReconstructedMesh;
	UPROPERTY(VisibleAnywhere, Category = "Preview")
	TObjectPtr<UCameraComponent> Camera;
	UPROPERTY(VisibleAnywhere, Category = "Preview")
	TObjectPtr<UTextRenderComponent> ReferenceLabel;
	UPROPERTY(VisibleAnywhere, Category = "Preview")
	TObjectPtr<UTextRenderComponent> ReconstructedLabel;
	UPROPERTY(VisibleAnywhere, Category = "Preview")
	TObjectPtr<UTextRenderComponent> StatusLabel;

	struct FClipResult
	{
		TArray<double> InferenceTimes;
		TArray<double> JointErrors;
		TArray<double> ModelAccelerations;
		TArray<double> SourceAccelerations;
		TArray<double> VelocityErrors;
		TArray<double> RotationErrors;
		uint64 Failures = 0;
		uint64 Fallbacks = 0;
		uint64 GameThreadSkips = 0;
		uint64 Discontinuities = 0;
	};
	TArray<FClipResult> ClipResults;
	FString OutputDirectory;
	double StartSeconds = 0.0;
	int32 ActiveAnimation = INDEX_NONE;
	int32 CapturedAnimation = INDEX_NONE;
	uint64 LastInferenceCount = 0;
	uint64 LastQualityCount = 0;
	TArray<double> InferenceTimes;
	TArray<double> EvaluationTimes;
	TArray<double> JointErrors;
	TArray<double> BaselineFrameTimes;
	TArray<double> ModelFrameTimes;
	TSet<uint32> WorkerThreadIds;
	bool bFinished = false;
};
