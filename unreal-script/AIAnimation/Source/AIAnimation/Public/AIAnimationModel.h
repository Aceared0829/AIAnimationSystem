// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "AIAnimationModel.generated.h"

class UNNEModelData;

/** 导出包中的 Root 相对参考骨骼；顺序与 ONNX 张量一致。 */
USTRUCT()
struct AIANIMATION_API FAIAnimationBone
{
	GENERATED_BODY()

	/** UE 骨骼名称。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	FName Name;

	/** 模型数组中的父索引，骨盆为 -1，其父由 RootBone 指定。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	int32 ParentIndex = INDEX_NONE;

	/** UE Root 相对参考变换，平移单位为 cm。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	FTransform ReferenceTransform;
};

/**
 * 固定骨架、采样率和窗口的 GPU 重建模型资产，由编辑器导入器创建。
 * 模型权重和契约一起保存；节点在 Game Thread 创建独立推理实例，动画工作线程只访问其数值快照。
 * 当前只支持已知姿态的 VQ 重建，不承诺 Pose 条件生成或网络位移。
 */
UCLASS(BlueprintType)
class AIANIMATION_API UAIAnimationModel final : public UDataAsset
{
	GENERATED_BODY()

public:
	/** ONNX 资产；模型会固定选择 NNERuntimeORTDml GPU 接口。 */
	UPROPERTY(VisibleAnywhere, Category = "Model")
	TObjectPtr<UNNEModelData> ModelData;

	/** 训练使用的骨架和归一化统计量签名。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	FString TrainingSignature;

	/** 导入时验证的 ONNX SHA-256。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	FString ModelSha256;

	/** 每次推理的历史帧数，必须为 8 到 64 之间的四倍数。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	int32 WindowFrames = 16;

	/** 模型原生采样率。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	float SampleRate = 30.0f;

	/** 由 Movement 或源动画持有的 Root 骨骼，模型不得修改。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	FName RootBone = TEXT("root");

	/** 按拓扑排序的骨盆及其后代。 */
	UPROPERTY(VisibleAnywhere, Category = "Contract")
	TArray<FAIAnimationBone> Bones;
};
