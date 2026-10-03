// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimationAsset.h"
#include "Animation/BlendProfile.h"

#include "Components/CapsuleComponent.h"

#include "UObject/ObjectPtr.h"

#include "CharacterMovementData.generated.h"

class UMotionWarpingComponent;

USTRUCT(BlueprintType,DisplayName="移动输入状态")
struct FMovementInputState
{
	[[nodiscard]] FMovementInputState(const bool bWantsToSprint, const bool bWantsToWalk, const bool bWantsToStrafe,
		const bool bWantsToAim, const bool bWantsToCrouch)
		: bWantsToSprint(bWantsToSprint),
		  bWantsToWalk(bWantsToWalk),
		  bWantsToStrafe(bWantsToStrafe),
		  bWantsToAim(bWantsToAim),
		  bWantsToCrouch(bWantsToCrouch)
	{
	}

	GENERATED_BODY()
	FMovementInputState() = default;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="想要冲刺")
	bool bWantsToSprint = false;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="想要走路")
	bool bWantsToWalk = false;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="想要扫射")
	bool bWantsToStrafe = true;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="想要瞄准")
	bool bWantsToAim = false;

	UPROPERTY(EditAnywhere,BlueprintReadWrite,DisplayName="想要蹲伏")
	bool bWantsToCrouch = false;

	auto operator<=>(const FMovementInputState&) const = default;

};

UENUM(BlueprintType,DisplayName="移动状态")
enum EMovementState
{
	Idle UMETA(DisplayName="闲置"),
	Moving UMETA(DisplayName="运动")
};

UENUM(BlueprintType,DisplayName="移动方向偏置")
enum EMovementDirectionBias
{
	LeftFootForward UMETA(DisplayName="左脚向前"),
	RightFootForward UMETA(DisplayName="右脚向前"),
};

UENUM(BlueprintType, DisplayName="步态")
enum EGait
{
	Walk UMETA(DisplayName="走路"),
	Run UMETA(DisplayName="跑步"),
	Sprint UMETA(DisplayName="冲刺"),
};

UENUM(BlueprintType,DisplayName="A移动模式")
enum EAMovementMode
{
	OnGround UMETA(DisplayName="地面上"),
	InAir UMETA(DisplayName="空中"),
	Sliding UMETA(DisplayName="滑行"),
	Traversing UMETA(DisplayName="穿越"),
};

UENUM(BlueprintType,DisplayName="旋转模式")
enum ERotationMode
{
	OrientToMovement UMETA(DisplayName="面向移动"),
	Strafe UMETA(DisplayName="扫射"),
	Aim UMETA(DisplayName="瞄准"),
};

UENUM(BlueprintType,DisplayName="站姿")
enum EStance
{
	Stand UMETA(DisplayName="站立"),
	Crouch UMETA(DisplayName="蹲伏"),
};

UENUM(BlueprintType,DisplayName="移动方向")
enum EMovementDirection
{
	F,
	B,
	LL,
	LR,
	RL,
	RR
};

UENUM(BlueprintType, DisplayName="模拟摇杆行为")
enum EAnalogStickBehavior
{
	FixedSpeed_SingleGait UMETA(DisplayName="固定速度-单步态"),
	FixedSpeed_WalkOrRun UMETA(DisplayName="固定速度-走或跑"),
	VariableSpeed_SingleGait UMETA(DisplayName="可变速度-单步态"),
	VariableSpeed_WalkAndRun UMETA(DisplayName="可变速度-走和跑"),
};

USTRUCT(BlueprintType,DisplayName="混合栈输入数据")
struct FBlendStackInputs
{
	[[nodiscard]] FBlendStackInputs():
	 Anim(nullptr),
	 bIsLoop(false),
	 StartTime(0.0),
	 BlendTime(0.0),
	 BlendProfile(nullptr),
	 Tags()
	{}

	[[nodiscard]] FBlendStackInputs(const TObjectPtr<UAnimationAsset>& Anim, const bool bIsLoop, const double StartTime,
	                                const double BlendTime, const TObjectPtr<UBlendProfile>& BlendProfile, const TArray<FName>& Tags)
		: Anim(Anim),
		  bIsLoop(bIsLoop),
		  StartTime(StartTime),
		  BlendTime(BlendTime),
		  BlendProfile(BlendProfile),
		  Tags(Tags)
	{
	}

	GENERATED_BODY()

	// 动画资源（可为空）
	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Anim", MakeStructureDefaultValue="None"))
	TObjectPtr<UAnimationAsset> Anim;

	// 是否循环播放
	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Loop", MakeStructureDefaultValue="False"))
	bool bIsLoop;

	// 起始播放时间（秒）
	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="StartTime", MakeStructureDefaultValue="0.000000"))
	double StartTime;

	// 混合过渡时长（秒）
	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="BlendTime", MakeStructureDefaultValue="0.000000"))
	double BlendTime;

	// 混合权重曲线配置（可为空）
	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="BlendProfile", MakeStructureDefaultValue="None"))
	TObjectPtr<UBlendProfile> BlendProfile;

	// 附加标签列表，用于筛选或标记
	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Tags"))
	TArray<FName> Tags;
};

USTRUCT(BlueprintType, DisplayName="用于动画的角色属性")
struct FCharacterPropertiesForAnimation
{

	GENERATED_BODY()
	[[nodiscard]] FCharacterPropertiesForAnimation():
	 InputState(false,false,true,false,false),
	 MovementMode(EAMovementMode::OnGround),
	 Stance(EStance::Stand),
	 RotationMode(ERotationMode::OrientToMovement),
	 Gait(EGait::Run),
	 MovementDirection(EMovementDirection::F),
	 ActorTransform(FTransform::Identity),
	 Velocity(FVector::ZeroVector),
	 InputAcceleration(FVector::ZeroVector),
	 CurrentMaxAcceleration(0.0),
	 CurrentMaxDeceleration(0.0),
	 OrientationIntent(FRotator::ZeroRotator),
	 AimingRotation(FRotator::ZeroRotator),
	 bJustLanded(false),
	 LandVelocity(FVector::ZeroVector),
	 SteeringTime(0.0),
	 GroundNormal(FVector::ZeroVector),
	 GroundLocation(FVector::ZeroVector)
	{}

	[[nodiscard]] FCharacterPropertiesForAnimation(const FMovementInputState& InputState,
		const TEnumAsByte<EAMovementMode>& MovementMode, const TEnumAsByte<EStance>& Stance,
		const TEnumAsByte<ERotationMode>& RotationMode, const TEnumAsByte<EGait>& Gait,
		const TEnumAsByte<EMovementDirection>& MovementDirection, const FTransform& ActorTransform,
		const FVector& Velocity, const FVector& InputAcceleration, const double CurrentMaxAcceleration,
		const double CurrentMaxDeceleration, const FRotator& OrientationIntent, const FRotator& AimingRotation,
		const bool bJustLanded, const FVector& LandVelocity, const double SteeringTime, const FVector& GroundNormal,
		const FVector& GroundLocation)
		: InputState(InputState),
		  MovementMode(MovementMode),
		  Stance(Stance),
		  RotationMode(RotationMode),
		  Gait(Gait),
		  MovementDirection(MovementDirection),
		  ActorTransform(ActorTransform),
		  Velocity(Velocity),
		  InputAcceleration(InputAcceleration),
		  CurrentMaxAcceleration(CurrentMaxAcceleration),
		  CurrentMaxDeceleration(CurrentMaxDeceleration),
		  OrientationIntent(OrientationIntent),
		  AimingRotation(AimingRotation),
		  bJustLanded(bJustLanded),
		  LandVelocity(LandVelocity),
		  SteeringTime(SteeringTime),
		  GroundNormal(GroundNormal),
		  GroundLocation(GroundLocation)
	{
	}

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="InputState"))
	FMovementInputState InputState;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="MovementMode", MakeStructureDefaultValue="OnGround"))
	TEnumAsByte<EAMovementMode> MovementMode;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Stance", MakeStructureDefaultValue="Stand"))
	TEnumAsByte<EStance> Stance;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="RotationMode", MakeStructureDefaultValue="OrientToMovement"))
	TEnumAsByte<ERotationMode> RotationMode;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Gait", MakeStructureDefaultValue="Run"))
	TEnumAsByte<EGait> Gait;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="MovementDirection", MakeStructureDefaultValue="F"))
	TEnumAsByte<EMovementDirection> MovementDirection;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="ActorTransform", MakeStructureDefaultValue="0.000000,0.000000,0.000000|0.000000,0.000000,0.000000|1.000000,1.000000,1.000000"))
	FTransform ActorTransform;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Velocity", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector Velocity;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="InputAcceleration", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector InputAcceleration;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="CurrentMaxAcceleration", MakeStructureDefaultValue="0.000000"))
	double CurrentMaxAcceleration;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="CurrentMaxDeceleration", MakeStructureDefaultValue="0.000000"))
	double CurrentMaxDeceleration;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="OrientationIntent", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FRotator OrientationIntent;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="AimingRotation", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FRotator AimingRotation;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="JustLanded", MakeStructureDefaultValue="False"))
	bool bJustLanded;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="LandVelocity", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector LandVelocity;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="SteeringTime", MakeStructureDefaultValue="0.000000"))
	double SteeringTime;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="GroundNormal", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector GroundNormal;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="GroundLocation", MakeStructureDefaultValue="0.000000,0.000000,0.000000"))
	FVector GroundLocation;

};


USTRUCT(BlueprintType, DisplayName="用于跑酷的角色属性")
struct  FCharacterPropertiesForTraversal
{
	GENERATED_BODY()
	[[nodiscard]] FCharacterPropertiesForTraversal():
	 Capsule(nullptr),
	 Mesh(nullptr),
	 MotionWarping(nullptr),
	 MovementMode(EAMovementMode::OnGround),
	 Gait(EGait::Walk),
	 Speed(0.0)
	{}

	[[nodiscard]] FCharacterPropertiesForTraversal(const TObjectPtr<UCapsuleComponent>& Capsule,
		const TObjectPtr<USkeletalMeshComponent>& Mesh,
		const TObjectPtr<UMotionWarpingComponent>& MotionWarping,
		const TEnumAsByte<EAMovementMode>& MovementMode,
		const TEnumAsByte<EGait>& Gait,
		const double Speed)
		: Capsule(Capsule),
		  Mesh(Mesh),
		  MotionWarping(MotionWarping),
		  MovementMode(MovementMode),
		  Gait(Gait),
		  Speed(Speed)
	{
	}

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Capsule", MakeStructureDefaultValue="None"))
	TObjectPtr<UCapsuleComponent> Capsule;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Mesh", MakeStructureDefaultValue="None"))
	TObjectPtr<USkeletalMeshComponent> Mesh;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="MotionWarping", MakeStructureDefaultValue="None"))
	TObjectPtr<UMotionWarpingComponent> MotionWarping;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="MovementMode", MakeStructureDefaultValue="OnGround"))
	TEnumAsByte<EAMovementMode> MovementMode;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Gait", MakeStructureDefaultValue="Walk"))
	TEnumAsByte<EGait> Gait;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, meta=(DisplayName="Speed", MakeStructureDefaultValue="0.000000"))
	double Speed;

};
