// Copyright ZhaoZining. All Rights Reserved.


#include "CharacterBase.h"
#include "GameplayTagContainer.h"
#include "KismetAnimationLibrary.h"
#include "MotionWarpingComponent.h"
#include "TimerManager.h"
#include "Animation/AnimBlueprint.h"
#include "Components/PreCMCTick.h"
#include "Components/SkeletalMeshComponent.h"
#include "Core/CameraAsset.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMathLibrary.h"
#include "CommonGameplay/Foley/FoleyEventsComponent.h"
#include "Net/UnrealNetwork.h"
#include "Sound/SoundWave.h"
#include "UObject/ConstructorHelpers.h"

// Sets default values
ACharacterBase::ACharacterBase()
{
	// Set this character to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	// 角色必须持续Tick以便在移动组件前插入自定义更新

	PreCMCTickComponent = CreateDefaultSubobject<UPreCMCTick>(TEXT("PreCMCTick"));
	// PreCMC用于在CharacterMovementComponent运行前执行回调
	checkf(PreCMCTickComponent,TEXT("PlayerCharacter必须拥有PreCMCTick组件"));

	MotionWarpingComponent = CreateDefaultSubobject<UMotionWarpingComponent>(TEXT("MotionWarpingComponent"));
	// MotionWarping驱动根运动与对齐逻辑
	checkf(MotionWarpingComponent,TEXT("PlayerCharacter必须拥有MotionWarping组件"));

	if (!FoleyEventsComp)
	{
		FoleyEventsComp = CreateDefaultSubobject<UFoleyEventsComponent>(TEXT("FoleyEventsComponent"));
		// FoleyEvents用于播放角色脚步音效等
		checkf(FoleyEventsComp,TEXT("PlayerCharacter必须拥有FoleyEvents组件"));
	}

	GetCharacterMovement()->bOrientRotationToMovement = false;
	GetCharacterMovement()->JumpZVelocity = 500.0f;
	GetCharacterMovement()->AirControl = 0.35f;
	GetCharacterMovement()->BrakingDecelerationFalling = 1500.0f;

	// 仅为 CharacterBase 自身保留示例默认资产，避免覆盖子类蓝图配置的 Mesh 和 AnimBP。
	if (GetClass() == ACharacterBase::StaticClass() && GetMesh())
	{
		GetMesh()->SetRelativeLocation(FVector{0.0f, 0.0f, -88.0f});
		GetMesh()->SetRelativeRotation(FRotator{0.0f, -90.0f, 0.0f});

		if (const ConstructorHelpers::FObjectFinder<USkeletalMesh> MeshPath
			(TEXT("/Script/Engine.SkeletalMesh'/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin.SKM_UEFN_Mannequin'"));
			MeshPath.Succeeded())
		{
			GetMesh()->SetSkeletalMeshAsset(MeshPath.Object);
		}

		if (const ConstructorHelpers::FObjectFinder<UAnimBlueprint> AnimBPPath
			(TEXT("/Script/Engine.AnimBlueprint'/Game/Blueprints/ABP_PlayerCharacter.ABP_PlayerCharacter'"));
			AnimBPPath.Succeeded() && AnimBPPath.Object->GeneratedClass)
		{
			GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
			GetMesh()->SetAnimInstanceClass(AnimBPPath.Object->GeneratedClass);
		}
	}

	if (const ConstructorHelpers::FObjectFinder<UCurveFloat> CurveFloatPath
		(TEXT("/Script/Engine.CurveFloat'/Game/Blueprints/Data/Curve_StrafeSpeedMap.Curve_StrafeSpeedMap'"));
		CurveFloatPath.Succeeded())
	{
		StrafeSpeedMappingCurve = CurveFloatPath.Object;
	}
	else
	{
		StrafeSpeedMappingCurve = nullptr;
	}

}

// Called when the game starts or when spawned
void ACharacterBase::BeginPlay()
{
	Super::BeginPlay();

	if (PreCMCTickComponent)
	{
		GetCharacterMovement()->AddTickPrerequisiteComponent(PreCMCTickComponent);
		// 在CMC Tick之前刷新旋转与移动配置
		PreCMCTickComponent->OnPreCMCTick.AddDynamic(this, &ACharacterBase::UpdateCMCRotation);
		PreCMCTickComponent->OnPreCMCTick.AddDynamic(this, &ACharacterBase::UpdateCMCMovement);
	}

	if (GetLocalRole()==ROLE_SimulatedProxy)
	{
		OnCharacterMovementUpdated.AddDynamic(this,&ACharacterBase::OnCharacterMovementUpdateEvent);
	}
}

void ACharacterBase::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	// 服务器上会进这里，但不要在服务器/非本地去做相机逻辑

	OnPossessedByClient_Event();

}

// Called every frame
void ACharacterBase::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
}

// Called to bind functionality to input
void ACharacterBase::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
}

void ACharacterBase::GetLifetimeReplicatedProps(TArray<class FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ACharacterBase,CharacterInputState);
}

void ACharacterBase::OnWalkingOffLedge_Implementation(const FVector& PreviousFloorImpactNormal,
	const FVector& PreviousFloorContactNormal, const FVector& PreviousLocation, float TimeDelta)
{
	Super::OnWalkingOffLedge_Implementation(PreviousFloorImpactNormal, PreviousFloorContactNormal, PreviousLocation,
	                                        TimeDelta);
	UnCrouch();
}

bool ACharacterBase::CanUpdateCMC_Implementation()
{
	return true;
}

void ACharacterBase::OnPossessedByClient_Event_Implementation()
{

}

bool ACharacterBase::CanUpdateCmc()
{
	return true;
}

void ACharacterBase::BuildMovementIntent(FCharacterMovementIntent& OutIntent) const
{
	OutIntent = FCharacterMovementIntent{};
	OutIntent.DesiredGait = GetDesiredGait();
	OutIntent.bHasMovementIntent = HasMovementInputVector();
	OutIntent.bUseControllerDesiredRotation = CharacterInputState.bWantsToStrafe || CharacterInputState.bWantsToAim;
	OutIntent.bOrientRotationToMovement = !OutIntent.bUseControllerDesiredRotation;
	OutIntent.bUseRequestedMoveAcceleration = true;

	const UCharacterMovementComponent* MovementComponent = GetCharacterMovement();
	if (MovementComponent)
	{
		OutIntent.MovementDirection = MovementComponent->GetPendingInputVector().GetSafeNormal2D();
		if (OutIntent.MovementDirection.IsNearlyZero())
		{
			OutIntent.MovementDirection = MovementComponent->GetCurrentAcceleration().GetSafeNormal2D();
		}
		if (OutIntent.MovementDirection.IsNearlyZero())
		{
			OutIntent.MovementDirection = MovementComponent->Velocity.GetSafeNormal2D();
		}
	}

	if (OutIntent.bOrientRotationToMovement)
	{
		FVector FacingDirection = FVector::ZeroVector;
		if (MovementComponent)
		{
			FacingDirection = MovementComponent->GetPendingInputVector().GetSafeNormal2D();
		}
		if (FacingDirection.IsNearlyZero() && OutIntent.bHasMovementIntent)
		{
			FacingDirection = OutIntent.MovementDirection;
		}
		if (FacingDirection.IsNearlyZero() && !IsLocallyControlled() && !OutIntent.MovementDirection.IsNearlyZero())
		{
			FacingDirection = OutIntent.MovementDirection;
		}

		if (!FacingDirection.IsNearlyZero())
		{
			OutIntent.OrientationIntent = FacingDirection.ToOrientationRotator();
			LastOrientToMovementIntent = OutIntent.OrientationIntent;
			bHasLastOrientToMovementIntent = true;
		}
		else if (bHasLastOrientToMovementIntent)
		{
			OutIntent.OrientationIntent = LastOrientToMovementIntent;
		}
		else
		{
			OutIntent.OrientationIntent = GetActorRotation();
			LastOrientToMovementIntent = OutIntent.OrientationIntent;
			bHasLastOrientToMovementIntent = true;
		}
	}
	else
	{
		OutIntent.OrientationIntent = GetControlRotation();
		LastOrientToMovementIntent = GetActorRotation();
		bHasLastOrientToMovementIntent = true;
	}
}

float ACharacterBase::CalculateBrakingDecelerationForMovementIntent(
	const FCharacterMovementIntent& MovementIntent) const
{
	return MovementIntent.bHasMovementIntent ? 500.0f : 2000.0f;
}

void ACharacterBase::UpdateCMCRotation()
{
	// 如果不能更新CMC，直接返回
	if (!CanUpdateCMC()||!CanUpdateCmc())
	{
		return;
	}
	FCharacterMovementIntent MovementIntent;
	BuildMovementIntent(MovementIntent);
	GetCharacterMovement()->bUseControllerDesiredRotation = MovementIntent.bUseControllerDesiredRotation;
	GetCharacterMovement()->bOrientRotationToMovement = MovementIntent.bOrientRotationToMovement;
	if (GetCharacterMovement()->IsFalling())
	{
		GetCharacterMovement()->RotationRate = FRotator(0.f,200.f,0.f);
	}
	else
	{
		GetCharacterMovement()->RotationRate = FRotator(0.0f, 360.0f, 0.0f);
	}
}

void ACharacterBase::UpdateCMCMovement()
{
	// 如果不能更新CMC，直接返回
	if (!CanUpdateCMC()||!CanUpdateCmc())
	{
		return;
	}
	FCharacterMovementIntent MovementIntent;
	BuildMovementIntent(MovementIntent);
	// CharacterBase 是 CMC 参数的唯一应用层，子类只提供当前帧运动意图。
	Gait = MovementIntent.DesiredGait;
	GetCharacterMovement()->bRequestedMoveUseAcceleration = MovementIntent.bUseRequestedMoveAcceleration;
	GetCharacterMovement()->MaxAcceleration = CalculateMaxAcceleration();
	GetCharacterMovement()->BrakingDecelerationWalking = CalculateBrakingDecelerationForMovementIntent(MovementIntent);
	GetCharacterMovement()->GroundFriction = CalculateGroundFriction();
	GetCharacterMovement()->MaxWalkSpeed = CalculateMaxSpeed();
	GetCharacterMovement()->MaxWalkSpeedCrouched = CalculateMaxCrouchSpeed();
}

void ACharacterBase::UpdateCharacterInputState_Server_Implementation(const FMovementInputState& NewMovementInputState)
{
	CharacterInputState = NewMovementInputState;
}

FVector2D ACharacterBase::GetMovementInputScaleValue(const FVector2D& InputVector2D) const
{
	const FVector2D InputVector2DNormalized = InputVector2D.GetSafeNormal();
	if (MovementStickMode == FixedSpeed_SingleGait || MovementStickMode == FixedSpeed_WalkOrRun)
	{
		// 固定速度模式仅需方向
		return InputVector2DNormalized;
	}
	else if (MovementStickMode == VariableSpeed_SingleGait || MovementStickMode == VariableSpeed_WalkAndRun)
	{
		// 可变速度模式保留原始幅度
		return InputVector2D;
	}
	return FVector2D::ZeroVector;
}


EGait ACharacterBase::GetDesiredGait() const
{
	FVector2D MoveActionValue(0.0f,0.0f);
	if (const UCharacterMovementComponent* CMC = GetCharacterMovement())
	{
		const FVector PendingInput = CMC->GetPendingInputVector();
		if (!PendingInput.IsNearlyZero())
		{
			MoveActionValue = FVector2D(PendingInput.X, PendingInput.Y);
		}
		else
		{
			const float MaxAccel = FMath::Max(CMC->GetMaxAcceleration(), KINDA_SMALL_NUMBER);
			const FVector NormalizedAccel = CMC->GetCurrentAcceleration() / MaxAccel;
			MoveActionValue = FVector2D(NormalizedAccel.X, NormalizedAccel.Y);
		}
	}

    const FVector2D MoveActionWorldSpaceValue = MoveActionValue;

	const bool bMoveMoreThanThreshold = MoveActionValue.Length() > AnalogWalkRunThreshold ||
		MoveActionWorldSpaceValue.Length() > AnalogWalkRunThreshold;
	bool FullMovementInput;
	if (MovementStickMode == FixedSpeed_SingleGait || MovementStickMode == VariableSpeed_SingleGait)
	{
		FullMovementInput = true;
	}
	else
	{
		// 根据摇杆幅度判断是否输入“全速”
		FullMovementInput = bMoveMoreThanThreshold;
	}

	if (CanSprint())
	{
		if (FullMovementInput)
		{
			return Sprint;
		}
		else
		{
			return Run;
		}
	}
	else
	{
		if (CharacterInputState.bWantsToWalk)
		{
			return Walk;
		}
		else
		{
			if (FullMovementInput)
			{
				return Run;
			}
			else
			{
				return Walk;
			}
		}
	}
}

float ACharacterBase::CalculateMaxAcceleration() const
{
	// 走/跑使用固定加速度，冲刺根据速度映射
	if (Gait == Walk)
	{
		return 800.0f;
	}
	else if (Gait == Run)
	{
		return 800.0f;
	}
	else //Gait == Sprint
	{
		return FMath::GetMappedRangeValueClamped(FVector2D{300.0f, 700.0f},
												 FVector2D{800.0f, 300.0f},
												 GetCharacterMovement()->Velocity.Length());
	}
}

float ACharacterBase::CalculateBrakingDeceleration() const
{
    if (HasMovementInputVector())
    {
        // 保持输入时降低制动提升流畅度
        return 500.0f;
    }
    return 2000.0f;
}

float ACharacterBase::CalculateGroundFriction() const
{
    if (Gait == Walk)
    {
        return 5.0f;
    }
    else if (Gait == Run)
    {
        return 5.0f;
    }
    else //Gait == Sprint
    {
        // 冲刺速度越快摩擦越低
        return FMath::GetMappedRangeValueClamped(FVector2D{0.0f, 500.0f},
                                                 FVector2D{5.0f, 3.0f},
                                                 GetCharacterMovement()->Velocity.Length());
    }
}

float ACharacterBase::CalculateMaxSpeed() const
{
	// 使用移动方向与角色朝向的夹角查询映射曲线
	const FVector CharacterVelocity = GetVelocity();
	const FRotator CharacterRotation = GetActorRotation();
	const float MoveDirectionAngle = UKismetAnimationLibrary::CalculateDirection(CharacterVelocity, CharacterRotation);
	const float MoveDirAngleAbs = FMath::Abs(MoveDirectionAngle);
	const float MoveDirAngleFloatValue = StrafeSpeedMappingCurve->GetFloatValue(MoveDirAngleAbs);

	float StrafeSpeedMap;
	if (GetCharacterMovement()->bOrientRotationToMovement)
	{
		StrafeSpeedMap = 0.0f;
	}
	else
	{
		StrafeSpeedMap = MoveDirAngleFloatValue;
	}
	FVector SpeedVector;
	if (Gait == Walk)
	{
		SpeedVector = WalkSpeed;
	}
	else if (Gait == Run)
	{
		SpeedVector = RunSpeed;
	}
	else //Gait == Sprint
	{
		SpeedVector = SprintSpeed;
	}

	if (StrafeSpeedMap < 1.0f)
	{
		return FMath::GetMappedRangeValueClamped(FVector2D{0.0f, 1.0f},
		                                         FVector2D{SpeedVector.X, SpeedVector.Y}, StrafeSpeedMap);
	}
	else
	{
		return FMath::GetMappedRangeValueClamped(FVector2D{1.0f, 2.0f},
		                                         FVector2D{SpeedVector.Y, SpeedVector.Z}, StrafeSpeedMap);
	}
}

float ACharacterBase::CalculateMaxCrouchSpeed() const
{
    // 蹲伏速度沿用同一映射逻辑
    const FVector CharacterVelocity = GetVelocity();
    const FRotator CharacterRotation = GetActorRotation();
    const float MoveDirectionAngle = UKismetAnimationLibrary::CalculateDirection(CharacterVelocity, CharacterRotation);
    const float MoveDirAngleAbs = FMath::Abs(MoveDirectionAngle);
    const float MoveDirAngleFloatValue = StrafeSpeedMappingCurve->GetFloatValue(MoveDirAngleAbs);

	float StrafeSpeedMap;
	if (GetCharacterMovement()->bOrientRotationToMovement)
	{
		StrafeSpeedMap = 0.0f;
	}
	else
	{
		StrafeSpeedMap = MoveDirAngleFloatValue;
	}
	if (StrafeSpeedMap<1.0f)
	{
		return FMath::GetMappedRangeValueClamped(FVector2D{0.0f,1.0f},
			FVector2D{CrouchSpeed.X,CrouchSpeed.Y},StrafeSpeedMap);
	}
	else
	{
		return FMath::GetMappedRangeValueClamped(FVector2D{1.0f,2.0f},
			FVector2D{CrouchSpeed.Y,CrouchSpeed.Z},StrafeSpeedMap);
	}
}

bool ACharacterBase::HasMovementInputVector() const
{
	return UKismetMathLibrary::NotEqual_VectorVector
	(GetPendingMovementInputVector(), FVector::ZeroVector, 0.0f);

}

bool ACharacterBase::CanSprint() const
{
	const UCharacterMovementComponent* CMC = GetCharacterMovement();
	if (!CMC)
	{
		return false;
	}

	const FVector CurrentAcceleration = CMC->GetCurrentAcceleration();
	const FVector PendingInput = CMC->GetPendingInputVector();

	const bool bLocal = IsLocallyControlled();
	const FVector ControllerAcceleration = bLocal ? PendingInput : CurrentAcceleration;

	if (ControllerAcceleration.IsNearlyZero())
	{
		return false;
	}

	const FRotator ControllerRotation = ControllerAcceleration.ToOrientationRotator();
	const FRotator DeltaRotation = UKismetMathLibrary::NormalizedDeltaRotator(GetActorRotation(), ControllerRotation);

	const bool bCanSprint = CMC->bOrientRotationToMovement || FMath::Abs(DeltaRotation.Yaw) < 50.0f;
	return bCanSprint && CharacterInputState.bWantsToSprint;
}

void ACharacterBase::OnCharacterMovementUpdateEvent(float DeltaTime, FVector OldLocation, FVector OldVelocity)
{
	UpdateMovementSimulated(OldVelocity);
}

void ACharacterBase::UpdateMovementSimulated(const FVector& OldVelocity)
{
	const bool bIsMovingOnGround = GetCharacterMovement()->IsMovingOnGround();
	if (bIsMovingOnGround!=bWasMovingOnGroundLastFrame_Simulated)
	{
		if (bIsMovingOnGround)
		{
			OnLanded_Event(OldVelocity);
			OnLanded_Event_Implementation(OldVelocity);
		}
		else
		{
			OnJumped_Event(OldVelocity.Length());
			OnJumped_Event_Implementation(OldVelocity.Length());
		}
	}
	bWasMovingOnGroundLastFrame_Simulated = bIsMovingOnGround;
}

void ACharacterBase::SetCharacterInputState_Implementation(FMovementInputState NewInputState)
{
	IInterface_PlayerCharacter::SetCharacterInputState_Implementation(NewInputState);
	CharacterInputState = NewInputState;
}

FCharacterPropertiesForAnimation ACharacterBase::GetCharacterPropertiesForAnimation_Implementation() const
{
	FCharacterPropertiesForAnimation Properties;
	FCharacterMovementIntent MovementIntent;
	BuildMovementIntent(MovementIntent);
	Properties.InputState = CharacterInputState;
	switch (GetCharacterMovement()->MovementMode)
	{
	case MOVE_None:
		Properties.MovementMode = OnGround;
		break;
	case MOVE_Walking:
		Properties.MovementMode = OnGround;
		break;
	case MOVE_NavWalking:
		Properties.MovementMode = OnGround;
		break;
	case MOVE_Falling:
		Properties.MovementMode = InAir;
		break;
	case MOVE_Swimming:
		Properties.MovementMode = InAir;
		break;
	case MOVE_Flying:
		Properties.MovementMode = InAir;
		break;
	case MOVE_Custom:
		Properties.MovementMode = InAir;
		break;
	case MOVE_MAX:
		Properties.MovementMode = InAir;
		break;
	}
	Properties.Stance = GetCharacterMovement()->IsCrouching() ? EStance::Crouch : EStance::Stand;
	Properties.RotationMode = GetCharacterMovement()->bOrientRotationToMovement
		                          ? OrientToMovement
		                          : Strafe;
	Properties.Gait = Gait;
	Properties.ActorTransform = GetActorTransform();
	Properties.Velocity = GetCharacterMovement()->Velocity;
	Properties.InputAcceleration = GetCharacterMovement()->GetCurrentAcceleration();
	if (Properties.InputAcceleration.IsNearlyZero()
		&& MovementIntent.bHasMovementIntent
		&& !MovementIntent.MovementDirection.IsNearlyZero())
	{
		// 导航路径可直接提交期望速度，此时 CMC 的 CurrentAcceleration 会保持为零。
		// 动画仍需收到等价的运动意图，否则会把高速移动误判为 Idle 并持续选择 Stop 姿态。
		Properties.InputAcceleration =
			MovementIntent.MovementDirection.GetSafeNormal2D() * GetCharacterMovement()->MaxAcceleration;
	}
	Properties.CurrentMaxAcceleration = GetCharacterMovement()->MaxAcceleration;
	Properties.CurrentMaxDeceleration = GetCharacterMovement()->BrakingDecelerationWalking;
	Properties.OrientationIntent = MovementIntent.OrientationIntent;
	Properties.AimingRotation = IsLocallyControlled() ? GetControlRotation() : GetBaseAimRotation();
	Properties.bJustLanded = bJustLanded;
	Properties.LandVelocity = LandVelocity;
	Properties.GroundNormal = GetCharacterMovement()->CurrentFloor.HitResult.ImpactNormal;

	return Properties;
}

FCharacterPropertiesForCamera ACharacterBase::GetCharacterPropertiesForCamera_Implementation() const
{
	FCharacterPropertiesForCamera Properties;
	Properties.CameraStyle = CameraStyle;
	Properties.CameraMode = CharacterInputState.bWantsToAim?ECameraMode::AimCam:CharacterInputState.bWantsToStrafe
	? ECameraMode::StrafeCam : ECameraMode::FreeCam;
	Properties.Gait = Gait;
	Properties.Stance = GetCharacterMovement()->IsCrouching() ? EStance::Crouch : EStance::Stand;
	return Properties;
}

FCharacterPropertiesForTraversal ACharacterBase::GetCharacterPropertiesForTraversal_Implementation() const
{
	FCharacterPropertiesForTraversal Properties;
	Properties.Capsule = GetCapsuleComponent();
	Properties.Mesh = GetMesh();
	Properties.MotionWarping = MotionWarpingComponent;

	switch (GetCharacterMovement()->MovementMode)
	{
	case MOVE_None:
		Properties.MovementMode = OnGround;
		break;
	case MOVE_Walking:
		Properties.MovementMode = OnGround;
		break;
	case MOVE_NavWalking:
		Properties.MovementMode = OnGround;
		break;
	case MOVE_Falling:
		Properties.MovementMode = InAir;
		break;
	case MOVE_Swimming:
		Properties.MovementMode = InAir;
		break;
	case MOVE_Flying:
		Properties.MovementMode = InAir;
		break;
	case MOVE_Custom:
		Properties.MovementMode = InAir;
		break;
	case MOVE_MAX:
		Properties.MovementMode = InAir;
		break;
	}
	Properties.Gait = Gait;
	Properties.Speed = GetCharacterMovement()->Velocity.Size2D();
	return Properties;
}

void ACharacterBase::OnJumped_Implementation()
{
	Super::OnJumped_Implementation();
	OnJumped_Event(GetCharacterMovement()->Velocity.Size2D());
}

void ACharacterBase::Landed(const FHitResult& Hit)
{
	Super::Landed(Hit);
	OnLanded_Event(GetCharacterMovement()->Velocity);
}

void ACharacterBase::OnJumped_Event_Implementation(float GroundSpeedBeforeJump)
{
	FFoleyEventParams FParams;
	FParams.Volume = FMath::GetMappedRangeValueClamped(FVector2D{0.0f,500.0f},
		FVector2D{0.5,1.0f},
		GroundSpeedBeforeJump);
	if (IsValid(FoleyEventsComp))
	{
		FoleyEventsComp->PlayFoleyEvent(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Jump")),FParams);
	}
}

void ACharacterBase::OnLanded_Event_Implementation(FVector InLandVelocity)
{
	FFoleyEventParams FParams;
	FParams.Volume = FMath::GetMappedRangeValueClamped(FVector2D{-500.0f,500.0f},
		FVector2D{0.5,1.5f},
		InLandVelocity.Z);
	if (IsValid(FoleyEventsComp))
	{
		FoleyEventsComp->PlayFoleyEvent(FGameplayTag::RequestGameplayTag(FName("Foley.Event.Land")),FParams);
	}
	bJustLanded = true;
	FTimerHandle LandTimerHandle;
	GetWorldTimerManager().SetTimer(LandTimerHandle, [this]()
	{
		bJustLanded = false;
	}, 0.3f, false);
}
