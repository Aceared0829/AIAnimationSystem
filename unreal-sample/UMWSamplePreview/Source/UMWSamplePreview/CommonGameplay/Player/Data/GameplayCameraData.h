// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "CharacterMovementData.h"

#include "UObject/Object.h"
#include "GameplayCameraData.generated.h"

UENUM(BlueprintType,DisplayName="摄像机模式")
enum ECameraMode
{
	FreeCam UMETA(DisplayName="自由摄像机"),
	StrafeCam UMETA(DisplayName="扫射摄像机"),
	AimCam UMETA(DisplayName="瞄准摄像机"),
	TwinStickCam UMETA(DisplayName="双摇杆摄像机"),
};

UENUM(BlueprintType,DisplayName="摄像机样式")
enum ECameraStyle
{
	Close UMETA(DisplayName="近距离"),
	Medium UMETA(DisplayName="中距离"),
	Far UMETA(DisplayName="远距离"),
	Debug UMETA(DisplayName="调试"),
};

USTRUCT(BlueprintType,DisplayName="用于摄像机的角色属性")
struct FCharacterPropertiesForCamera
{
	GENERATED_BODY()
	[[nodiscard]] FCharacterPropertiesForCamera():
	 CameraStyle(ECameraStyle::Far),
	 CameraMode(ECameraMode::FreeCam),
	 Gait(EGait::Walk),
	 Stance(EStance::Stand)
	{}

	[[nodiscard]] FCharacterPropertiesForCamera(const TEnumAsByte<ECameraStyle>& CameraStyle,
	                                            const TEnumAsByte<ECameraMode>& CameraMode,
	                                            const TEnumAsByte<EGait>& Gait,
	                                            const TEnumAsByte<EStance>& Stance)
		: CameraStyle(CameraStyle),
		  CameraMode(CameraMode),
		  Gait(Gait),
		  Stance(Stance)
	{
	}

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="CameraStyle", MakeStructureDefaultValue="NewEnumerator0"))
	TEnumAsByte<ECameraStyle> CameraStyle;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="CameraMode", MakeStructureDefaultValue="NewEnumerator0"))
	TEnumAsByte<ECameraMode> CameraMode;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Gait", MakeStructureDefaultValue="Walk"))
	TEnumAsByte<EGait> Gait;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Stance", MakeStructureDefaultValue="Stand"))
	TEnumAsByte<EStance> Stance;

};
