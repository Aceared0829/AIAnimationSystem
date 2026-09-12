// Copyright ZhaoZining. All Rights Reserved.

/** 动画训练数据的编辑器导出配置；仅在下一次导出时读取。 */
#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "AILocomotionDatasetSettings.generated.h"

/** 在项目设置中指定身体根骨骼与左右脚；配置仅供编辑器使用，不参与网络复制。 */
UCLASS(Config=Editor, DefaultConfig, meta=(DisplayName="AI Locomotion 动画数据"))
class AILOCOMOTIONDATASETEDITOR_API UAILocomotionDatasetSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	/** 只承载角色整体运动的 UE Root；导出时从身体姿态中剥离，并单独写入审计轨道。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName RootBone = TEXT("root");

	/** 作为模型身体根节点的骨盆。导出该骨骼及全部子骨骼，并保存为相对 UE Root 的姿态。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName PelvisBone = TEXT("pelvis");

	/** 左髋关节；与右髋一起确定角色朝向。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName LeftHipBone = TEXT("thigh_l");

	/** 右髋关节，必须与左髋不同。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName RightHipBone = TEXT("thigh_r");

	/** 左脚踝接触点。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName LeftFootBone = TEXT("foot_l");

	/** 左前脚掌接触点。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName LeftToeBone = TEXT("ball_l");

	/** 右脚踝接触点。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName RightFootBone = TEXT("foot_r");

	/** 右前脚掌接触点。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName RightToeBone = TEXT("ball_r");

	/** 左手运行时 IK 的语义骨骼；必须位于骨盆子树且不能与其他语义骨骼重复。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName LeftHandBone = TEXT("hand_l");

	/** 右手运行时 IK 的语义骨骼；必须位于骨盆子树且不能与其他语义骨骼重复。 */
	UPROPERTY(Config, EditAnywhere, Category="Skeleton")
	FName RightHandBone = TEXT("hand_r");

	/** 兼容旧配置的保留字段；导出始终读取源 AnimDataModel 的帧率，此值不再控制采样。 */
	UPROPERTY(Config)
	int32 SampleRate = 30;

	/** 单个片段允许的最大采样帧数；超出时拒绝导出，避免意外的大任务。 */
	UPROPERTY(Config, EditAnywhere, Category="Sampling", meta=(ClampMin="2", ClampMax="18000", UIMin="2", UIMax="18000"))
	int32 MaxFramesPerClip = 3600;
};
