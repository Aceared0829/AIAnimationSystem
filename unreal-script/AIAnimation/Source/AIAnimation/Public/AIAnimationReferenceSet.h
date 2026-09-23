// Copyright ZhaoZining. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "AIAnimationReferenceSet.generated.h"

class UAnimSequence;

/**
 * 一段动画的硬姿态参考配置。帧号指向原始动画的 30 Hz 源帧；运行时在对应帧读取源局部姿态。
 * 资产只保存创作数据，不保存当前播放位置或预览开关。不同动画必须使用各自的资产。
 */
UCLASS(BlueprintType)
class AIANIMATION_API UAIAnimationReferenceSet final : public UDataAsset
{
	GENERATED_BODY()

public:
	/** 参考帧所属的源动画；预览时须与所选动画一致。 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Reference")
	TSoftObjectPtr<UAnimSequence> Animation;

	/** 已选源帧号；保存时按升序去重，负数或超出动画范围的值无效。 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Reference")
	TArray<int32> Frames;

	/** 配置格式版本；为以后增加独立姿态数据保留迁移入口。 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Reference")
	int32 FormatVersion = 1;
};
