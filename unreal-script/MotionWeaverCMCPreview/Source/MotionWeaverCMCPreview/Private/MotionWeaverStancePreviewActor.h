// Copyright ZhaoZining. All Rights Reserved.

/**
 * @file MotionWeaverStancePreviewActor.h
 * @brief 声明单机 B1 姿态推理和 CMC Root 绑定的实验预览 Actor。
 */

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "NNE.h"
#include "NNERuntimeGPU.h"
#include "MotionWeaverStancePreviewActor.generated.h"

class ACharacter;
class UNNEModelData;
class UPoseableMeshComponent;
class USceneComponent;

/**
 * 从第一个本地玩家的已执行 CMC Root 和站蹲状态构造在线条件，使用本机 DirectML 生成姿态。
 *
 * 以 -MotionWeaverModelFolder=<导出目录> 启用；目录必须包含 model.onnx 与 manifest.json。
 * 模型 Mesh 只替换原 Mesh 的视觉显示，不产生 Root Motion，不修改 Character 胶囊体或 CMC。
 * 源 Mesh 继续求值用于 24 帧历史，首次成功推理后才隐藏；失败时恢复源 Mesh。
 * 当前未来 Root 是恒速短时外推，训练用的却是真值 Root，因此仅用于单机探索。
 * 运行时按游戏 Tick 最多采一个 30 Hz 历史点，低帧率不是固定采样；无联机复制。
 */
UCLASS()
class MOTIONWEAVERCMCPREVIEW_API AMotionWeaverStancePreviewActor final : public AActor
{
	GENERATED_BODY()

public:
	AMotionWeaverStancePreviewActor();
	bool HasProducedPose() const { return NumInferences > 0 && bPoseVisible; }
	int32 GetNumInferences() const { return NumInferences; }
	int32 GetNumInferenceFailures() const { return NumInferenceFailures; }

protected:
	//~ Begin AActor Interface
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	//~ End AActor Interface

private:
	struct FBoneContract
	{
		FName Name;
		int32 ParentIndex = INDEX_NONE;
		FVector ReferencePositionCm = FVector::ZeroVector;
		FQuat ReferenceRotation = FQuat::Identity;
	};

	bool LoadModel(const FString& Folder);
	bool CaptureHistory(const ACharacter& Character);
	bool InferFuture(const ACharacter& Character);
	bool ApplyPredictedPose(const ACharacter& Character);
	void RestoreSourceMesh();
	void SaveTelemetry() const;

	UPROPERTY(VisibleAnywhere, Category = "MotionWeaver")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(VisibleAnywhere, Category = "MotionWeaver")
	TObjectPtr<UPoseableMeshComponent> ModelMesh;

	UPROPERTY(Transient)
	TObjectPtr<UNNEModelData> ModelData;

	TSharedPtr<UE::NNE::IModelInstanceGPU> Instance;
	TWeakObjectPtr<ACharacter> TrackedCharacter;
	TArray<FBoneContract> Bones;
	TArray<FVector> PoseMeanMeters;
	TArray<FVector> PoseStdMeters;
	TArray<float> History;
	TArray<FTransform> HistoryRoots;
	TArray<float> FutureRoot;
	TArray<float> GoalStance;
	TArray<float> Prediction;
	TArray<FString> TelemetryRows;
	float SampleRemainderSeconds = 0.0f;
	float ElapsedSeconds = 0.0f;
	float LastInferenceMilliseconds = 0.0f;
	int32 NumHistoryFrames = 0;
	int32 NumInferences = 0;
	int32 NumInferenceFailures = 0;
	int32 LastRecordedInference = 0;
	int32 SamplesSinceInference = 0;
	bool bPoseVisible = false;
	bool bEnabled = false;
	bool bUseFeedback = false;
};
